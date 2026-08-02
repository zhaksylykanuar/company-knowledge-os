"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import type { FormEvent } from "react";
import { useEffect, useRef, useState } from "react";

import { enrollFounder, EnrollmentError } from "../../lib/auth";
import {
  companyNameToSlug,
  enrollmentTokenFromLocation
} from "../../lib/enrollment";
import styles from "./start.module.css";

type FounderEnrollmentFormProps = {
  token: string;
  onEnrolled: () => void;
};

export function FounderEnrollmentForm({
  token,
  onEnrolled
}: FounderEnrollmentFormProps) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [companySlug, setCompanySlug] = useState("");
  const [slugEdited, setSlugEdited] = useState(false);
  const [password, setPassword] = useState("");
  const [passwordConfirmation, setPasswordConfirmation] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (password !== passwordConfirmation) {
      setError("Пароли не совпадают. Проверьте оба поля.");
      return;
    }

    setPending(true);
    try {
      await enrollFounder({
        token,
        email: email.trim(),
        name: name.trim(),
        password,
        workspaceName: companyName.trim(),
        workspaceSlug: companySlug.trim()
      });
      onEnrolled();
    } catch (caught) {
      setError(
        caught instanceof EnrollmentError
          ? caught.message
          : "Не удалось создать компанию. Данные не сохранены — попробуйте ещё раз."
      );
      setPending(false);
    }
  }

  function onCompanyNameChange(value: string) {
    setCompanyName(value);
    if (!slugEdited) {
      setCompanySlug(companyNameToSlug(value));
    }
  }

  return (
    <form className={styles.form} onSubmit={onSubmit} aria-label="Создать компанию">
      <div className={styles.formHeading}>
        <p className={styles.step}>Ссылка приглашения получена</p>
        <h1>Создадим вашу компанию?</h1>
        <p>
          Один аккаунт, одно рабочее пространство и понятная карта происходящего.
          Никаких настроек через терминал.
        </p>
      </div>

      <div className={styles.fields}>
        <label>
          <span>Как называется компания?</span>
          <input
            autoComplete="organization"
            maxLength={255}
            name="workspace_name"
            onChange={(event) => onCompanyNameChange(event.target.value)}
            placeholder="Например, Atlas Studio"
            required
            value={companyName}
          />
        </label>

        <div className={styles.twoColumns}>
          <label>
            <span>Как к вам обращаться?</span>
            <input
              autoComplete="name"
              maxLength={160}
              name="name"
              onChange={(event) => setName(event.target.value)}
              placeholder="Имя"
              required
              value={name}
            />
          </label>
          <label>
            <span>Рабочая почта</span>
            <input
              autoComplete="email"
              maxLength={320}
              name="email"
              onChange={(event) => setEmail(event.target.value)}
              placeholder="you@company.com"
              required
              type="email"
              value={email}
            />
          </label>
        </div>

        <div className={styles.twoColumns}>
          <label>
            <span>Придумайте пароль</span>
            <input
              autoComplete="new-password"
              maxLength={256}
              minLength={8}
              name="password"
              onChange={(event) => setPassword(event.target.value)}
              required
              type="password"
              value={password}
            />
          </label>
          <label>
            <span>Повторите пароль</span>
            <input
              autoComplete="new-password"
              maxLength={256}
              minLength={8}
              name="password_confirmation"
              onChange={(event) => setPasswordConfirmation(event.target.value)}
              required
              type="password"
              value={passwordConfirmation}
            />
          </label>
        </div>

        <details className={styles.advanced}>
          <summary>Адрес рабочего пространства</summary>
          <label>
            <span>Короткий адрес</span>
            <div className={styles.slugField}>
              <span>founderos /</span>
              <input
                aria-describedby="workspace-slug-help"
                maxLength={120}
                name="workspace_slug"
                onChange={(event) => {
                  setSlugEdited(true);
                  setCompanySlug(companyNameToSlug(event.target.value));
                }}
                pattern="[a-z0-9]+(?:-[a-z0-9]+)*"
                required
                value={companySlug}
              />
            </div>
            <small id="workspace-slug-help">
              Мы заполнили адрес автоматически. Меняйте его только если нужно.
            </small>
          </label>
        </details>
      </div>

      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}

      <button className={styles.primaryButton} disabled={pending} type="submit">
        {pending ? "Создаём безопасно…" : "Создать компанию"}
      </button>
      <p className={styles.loginLink}>
        Уже есть аккаунт? <Link href="/login">Войти</Link>
      </p>
    </form>
  );
}

function InvalidInvite() {
  return (
    <section className={styles.invalidCard} aria-labelledby="invalid-invite-title">
      <div className={styles.logoMark} aria-hidden="true">
        F
      </div>
      <p className={styles.step}>Нужна новая ссылка</p>
      <h1 id="invalid-invite-title">Приглашение не найдено</h1>
      <p>
        Откройте полную одноразовую ссылку от администратора FounderOS. Без неё
        регистрация закрыта.
      </p>
      <Link className={styles.secondaryButton} href="/login">
        У меня уже есть аккаунт
      </Link>
    </section>
  );
}

export default function StartPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const capturedToken = useRef<string | null | undefined>(undefined);

  useEffect(() => {
    // React StrictMode replays effects in development. The ref keeps the first
    // captured bearer across that replay after the URL has already been cleaned.
    if (capturedToken.current === undefined) {
      capturedToken.current = enrollmentTokenFromLocation(window.location);
      // Keep the bearer only in this mounted page state. Removing the fragment
      // prevents accidental copying/screenshots after the link has been opened;
      // it was never sent to the server in the first place.
      if (window.location.hash || window.location.search) {
        window.history.replaceState(null, "", window.location.pathname);
      }
    }
    setToken(capturedToken.current);
  }, []);

  return (
    <main className={styles.page}>
      <aside className={styles.story} aria-label="Что будет дальше">
        <Link className={styles.brand} href="/login" aria-label="FounderOS">
          <span aria-hidden="true">F</span>
          FounderOS
        </Link>
        <div>
          <p className={styles.storyKicker}>Первые 10 минут</p>
          <h2>Компания станет видимой.</h2>
          <ol>
            <li><span>01</span>Создадим безопасное пространство</li>
            <li><span>02</span>Подключим первый реальный источник</li>
            <li><span>03</span>Соберём карту людей и компаний</li>
          </ol>
        </div>
        <p className={styles.safetyNote}>
          Доступ только по одноразовому приглашению. FounderOS не выполняет внешние
          действия без подтверждения.
        </p>
      </aside>
      <section className={styles.formSide}>
        {token === undefined ? (
          <p className={styles.loading} aria-busy="true">
            Открываем защищённую форму…
          </p>
        ) : token ? (
          <FounderEnrollmentForm
            onEnrolled={() => router.replace("/onboarding")}
            token={token}
          />
        ) : (
          <InvalidInvite />
        )}
      </section>
    </main>
  );
}
