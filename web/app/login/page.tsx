"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { LoginError, login } from "../../lib/auth";
import { M } from "../../lib/messages";
import styles from "./login.module.css";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(email, password);
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof LoginError ? err.message : M.auth.loginFailedUnknown);
      setPending(false);
    }
  }

  return (
    <main className={styles.page}>
      <aside className={styles.story} aria-label="Что ждёт внутри FounderOS">
        <div className={styles.brand}>
          <span aria-hidden="true">F</span>
          FounderOS
        </div>
        <div className={styles.storyCopy}>
          <p>Компания в движении</p>
          <h1>Один экран. Один следующий ход.</h1>
          <ol aria-label="Основные зоны FounderOS">
            <li><span>01</span>Сегодня — что важно прямо сейчас</li>
            <li><span>02</span>Компания — люди, организации и связи</li>
            <li><span>03</span>Решения — что требует вашего ответа</li>
          </ol>
        </div>
        <p className={styles.boundary}>
          FounderOS показывает только сохранённые факты и не выполняет внешние
          действия без явного подтверждения.
        </p>
      </aside>

      <section className={styles.formSide}>
        <form className={styles.card} onSubmit={onSubmit} aria-label={M.auth.signIn}>
          <p className={styles.eyebrow}>С возвращением</p>
          <h2>{M.auth.title}</h2>
          <p className={styles.subtitle}>{M.auth.subtitle}</p>

          <div className={styles.fields}>
            <label>
              <span>{M.auth.email}</span>
              <input
                maxLength={320}
                type="text"
                name="username"
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                autoFocus
              />
            </label>
            <label>
              <span>{M.auth.password}</span>
              <span className={styles.passwordField}>
                <input
                  maxLength={256}
                  type={passwordVisible ? "text" : "password"}
                  name="password"
                  autoComplete="current-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                />
                <button
                  aria-label={passwordVisible ? "Скрыть пароль" : "Показать пароль"}
                  className={styles.passwordToggle}
                  onClick={() => setPasswordVisible((current) => !current)}
                  type="button"
                >
                  {passwordVisible ? "Скрыть" : "Показать"}
                </button>
              </span>
            </label>
          </div>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <button className={styles.submit} type="submit" disabled={pending}>
            {pending ? M.auth.signingIn : M.auth.signIn}
            <span aria-hidden="true">→</span>
          </button>
          <p className={styles.inviteNote}>
            Первый вход? Откройте одноразовую ссылку, которую выдал администратор.
            Регистрация без приглашения закрыта.
          </p>
        </form>
      </section>
    </main>
  );
}
