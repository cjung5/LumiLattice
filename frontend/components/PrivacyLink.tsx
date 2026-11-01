import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

export function PrivacyLink() {
  const t = useTranslations("Auth");
  return (
    <footer className="text-xs text-muted">
      <Link className="underline" href="/privacy">
        {t("privacy")}
      </Link>
    </footer>
  );
}
