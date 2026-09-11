import type {
  AuthResponse,
  HealthResponse,
  ScreeningResponse,
  User,
  UserSettings,
} from "./types";

const BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL ?? ""
).replace(/\/+$/, "");

export const TOKEN_STORAGE_KEY = "cvparser.accessToken";

/**
 * A non-2xx response from the backend.
 *
 * FastAPI's `detail` is a string for most of our errors, a list of field
 * errors for request-validation failures, and an object for the
 * "no readable resumes" case — `message` flattens all three.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  /** True when the token is missing, expired, or signed with another secret. */
  get isUnauthenticated(): boolean {
    return this.status === 401;
  }
}

export function readStoredToken(): string | null {
  if (typeof window === "undefined") return null;

  return window.localStorage.getItem(TOKEN_STORAGE_KEY);
}

export function storeToken(token: string | null): void {
  if (typeof window === "undefined") return;

  if (token) {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } else {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  }
}

interface RequestOptions {
  method?: string;
  /** Serialised as JSON; omit when sending `form`. */
  body?: unknown;
  form?: FormData;
  token?: string | null;
  signal?: AbortSignal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, form, token, signal } = options;

  const headers: Record<string, string> = {};

  // FormData sets its own multipart boundary; setting Content-Type by hand
  // would produce a boundary-less header the backend cannot parse.
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;

  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;

    // fetch only rejects for transport-level problems, which from the browser
    // means the backend is down, unreachable, or refusing the origin.
    throw new ApiError(
      0,
      null,
      `Could not reach the API at ${BASE_URL}. Is the backend running?`,
    );
  }

  if (response.status === 204) return undefined as T;

  const payload = await readBody(response);

  if (!response.ok) {
    const detail = isRecord(payload) ? payload.detail : payload;

    throw new ApiError(response.status, detail, flattenDetail(detail, response));
  }

  return payload as T;
}

async function readBody(response: Response): Promise<unknown> {
  const text = await response.text();

  if (!text) return null;

  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function flattenDetail(detail: unknown, response: Response): string {
  if (typeof detail === "string" && detail) return detail;

  // Pydantic validation errors: [{ loc: [...], msg: "..." }, ...]
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => (isRecord(item) ? String(item.msg ?? "") : String(item)))
      .filter(Boolean);

    if (messages.length) return messages.join("; ");
  }

  if (isRecord(detail) && typeof detail.message === "string") {
    return detail.message;
  }

  return `Request failed with status ${response.status}.`;
}

// ---------------------------------------------------------------------------
// Endpoints
// ---------------------------------------------------------------------------

export const api = {
  health(): Promise<HealthResponse> {
    return request<HealthResponse>("/health");
  },

  signup(input: {
    email: string;
    password: string;
    fullName: string;
  }): Promise<AuthResponse> {
    return request<AuthResponse>("/api/v1/auth/signup", {
      method: "POST",
      body: input,
    });
  },

  login(input: { email: string; password: string }): Promise<AuthResponse> {
    return request<AuthResponse>("/api/v1/auth/login", {
      method: "POST",
      body: input,
    });
  },

  me(token: string): Promise<User> {
    return request<User>("/api/v1/auth/me", { token });
  },

  updateMe(
    token: string,
    input: { fullName?: string; settings?: UserSettings },
  ): Promise<User> {
    return request<User>("/api/v1/auth/me", {
      method: "PATCH",
      body: input,
      token,
    });
  },

  /**
   * `POST /api/v1/screenings`. Exactly one of `jobDescriptionText` and
   * `jobDescriptionFile` must be set — the backend rejects both and neither
   * with a 422.
   */
  createScreening(
    input: {
      resumes: File[];
      jobDescriptionText?: string;
      jobDescriptionFile?: File | null;
      positionTitle?: string;
    },
    options: { token?: string | null; signal?: AbortSignal } = {},
  ): Promise<ScreeningResponse> {
    const form = new FormData();

    for (const resume of input.resumes) form.append("resumes", resume);

    if (input.jobDescriptionFile) {
      form.append("job_description_file", input.jobDescriptionFile);
    } else if (input.jobDescriptionText?.trim()) {
      form.append("job_description_text", input.jobDescriptionText);
    }

    if (input.positionTitle?.trim()) {
      form.append("position_title", input.positionTitle.trim());
    }

    return request<ScreeningResponse>("/api/v1/screenings", {
      method: "POST",
      form,
      token: options.token,
      signal: options.signal,
    });
  },
};

export { BASE_URL as API_BASE_URL };
