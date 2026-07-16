"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { logout } from "../../lib/auth";
import { useSession } from "../../lib/session";
import styles from "./onboarding.module.css";

export function OnboardingRecoveryView({ onSignOut }: { onSignOut: () => void }) {
  return (
    <div className={styles.recoveryPage}>
      <section className={styles.recoveryCard}>
        <span className={styles.recoveryMark} aria-hidden="true">!</span>
        <p className={styles.kicker}>Аккаунт пока без компании</p>
        <h1>Компания пока не привязана к аккаунту.</h1>
        <p className={styles.lead}>
          Мы не будем угадывать рабочее пространство или создавать его без разрешения.
          Сообщите администратору почту этого аккаунта и попросите добавить вас в
          нужную компанию. Новая ссылка основателя создаёт другой аккаунт и не
          исправит эту привязку.
        </p>
        <button className={styles.primaryAction} onClick={onSignOut} type="button">
          Выйти из аккаунта
        </button>
      </section>
    </div>
  );
}

/**
 * Workspace-scoped onboarding lives inside the Headquarters snapshot. This
 * route remains only as the safe pre-workspace recovery boundary and as a
 * compatibility entry point for older invite links.
 */
export default function OnboardingPage() {
  const router = useRouter();
  const session = useSession();
  const workspaceId = session?.workspaceId ?? null;

  useEffect(() => {
    if (workspaceId) {
      router.replace("/dashboard?onboarding=1");
    }
  }, [router, workspaceId]);

  if (session && workspaceId === null) {
    return (
      <OnboardingRecoveryView
        onSignOut={() => {
          void logout().finally(() => router.replace("/login"));
        }}
      />
    );
  }

  return (
    <div className={styles.loadingPage} aria-busy="true">
      <div className={styles.loadingPulse} />
      <p>Открываем живой штаб компании…</p>
    </div>
  );
}
