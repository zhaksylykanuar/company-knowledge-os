"use client";

import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { setupPassword } from "../../lib/auth";
import { setupTokenFromLocation } from "../../lib/enrollment";
import { M } from "../../lib/messages";
import styles from "../login/login.module.css";

export default function SetupPasswordPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const capturedToken = useRef<string | null | undefined>(undefined);
  const [password, setPassword] = useState("");
  const [passwordVisible, setPasswordVisible] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (capturedToken.current === undefined) {
      capturedToken.current = setupTokenFromLocation(window.location);
      if (window.location.hash || window.location.search) {
        window.history.replaceState(null, "", window.location.pathname);
      }
    }
    setToken(capturedToken.current);
  }, []);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) {
      setError(M.auth.setupMissingToken);
      return;
    }
    setError(null);
    setPending(true);
    try {
      await setupPassword(token, password);
      router.replace("/");
    } catch {
      setError(M.auth.setupFailed);
      setPending(false);
    }
  }

  return (
    <main className={styles.page}>
      <aside className={styles.story} aria-label="Что произойдёт после входа">
        <div className={styles.brand}>
          <span aria-hidden="true">F</span>
          FounderOS
        </div>
        <div className={styles.storyCopy}>
          <p>Последний шаг</p>
          <h1>Ваша роль уже ждёт внутри.</h1>
          <ol aria-label="Что будет дальше">
            <li><span>01</span>Создайте личный пароль</li>
            <li><span>02</span>Откройте выбранную компанию</li>
            <li><span>03</span>Увидьте факты, людей и решения</li>
          </ol>
        </div>
        <p className={styles.boundary}>
          Ссылка одноразовая. FounderOS не хранит её открыто и удаляет из адреса
          сразу после открытия.
        </p>
      </aside>

      <section className={styles.formSide}>
        <form className={styles.card} onSubmit={onSubmit} aria-label={M.auth.setupSubmit}>
          <p className={styles.eyebrow}>Приглашение в команду</p>
          <h2>{M.auth.setupTitle}</h2>
          <p className={styles.subtitle}>{M.auth.setupSubtitle}</p>

          <div className={styles.fields}>
            <label>
              <span>{M.auth.setupPassword}</span>
              <span className={styles.passwordField}>
                <input
                  autoComplete="new-password"
                  maxLength={256}
                  minLength={8}
                  onChange={(event) => setPassword(event.target.value)}
                  required
                  type={passwordVisible ? "text" : "password"}
                  value={password}
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

          {token === undefined ? (
            <p className={styles.inviteNote} aria-busy="true">
              Открываем одноразовую ссылку…
            </p>
          ) : null}
          {token === null ? (
            <p className={styles.error} role="alert">
              {M.auth.setupMissingToken}
            </p>
          ) : null}
          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <button className={styles.submit} disabled={pending || !token} type="submit">
            {pending ? M.auth.setupSubmitting : M.auth.setupSubmit}
            <span aria-hidden="true">→</span>
          </button>
          <p className={styles.inviteNote}>
            Если ссылка недействительна, попросите владельца или администратора
            компании создать новую.
          </p>
        </form>
      </section>
    </main>
  );
}
