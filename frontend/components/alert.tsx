import { AlertIcon, CheckIcon } from "./icons";

type Tone = "error" | "warning" | "success";

const TONE_STYLE: Record<Tone, string> = {
  error: "border-negative/30 bg-negative/8 text-negative",
  warning: "border-caution/30 bg-caution/8 text-caution",
  success: "border-positive/30 bg-positive/8 text-positive",
};

export function Alert({
  tone = "error",
  title,
  children,
}: {
  tone?: Tone;
  title?: string;
  children: React.ReactNode;
}) {
  const Icon = tone === "success" ? CheckIcon : AlertIcon;

  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      className={`flex gap-2.5 rounded-lg border p-3 text-[13px] ${TONE_STYLE[tone]}`}
    >
      <Icon size={16} className="mt-0.5 shrink-0" />
      <div className="min-w-0">
        {title ? <p className="font-semibold">{title}</p> : null}
        <div className="[&_p]:leading-relaxed">{children}</div>
      </div>
    </div>
  );
}
