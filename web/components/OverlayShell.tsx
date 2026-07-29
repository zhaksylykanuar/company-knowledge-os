"use client";

import type {
  MouseEvent as ReactMouseEvent,
  ReactNode,
  RefObject
} from "react";
import { useEffect, useId, useRef } from "react";
import { createPortal } from "react-dom";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  "[contenteditable='true']",
  "[tabindex]:not([tabindex='-1'])"
].join(",");

type OverlayMode = "drawer" | "modal";

type OverlayShellProps = {
  backgroundRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  closeDisabled?: boolean;
  closeLabel?: string;
  label: string;
  mode: OverlayMode;
  onClose: () => void;
};

type AttributeTarget = {
  getAttribute: (name: string) => string | null;
  removeAttribute: (name: string) => void;
  setAttribute: (name: string, value: string) => void;
};

type ScrollLockTarget = {
  style: { overflow: string };
};

/**
 * Applies the two global overlay boundaries and restores their exact previous
 * values. Exported so the lifecycle can be verified without a DOM test shim.
 */
export function lockOverlayEnvironment(
  background: AttributeTarget | readonly AttributeTarget[] | null,
  body: ScrollLockTarget
): () => void {
  const previousOverflow = body.style.overflow;
  const backgrounds = Array.isArray(background)
    ? background
    : background
      ? [background]
      : [];
  const previousAttributes = backgrounds.map((target) => ({
    ariaHidden: target.getAttribute("aria-hidden"),
    inert: target.getAttribute("inert"),
    target
  }));

  body.style.overflow = "hidden";
  for (const target of backgrounds) {
    target.setAttribute("aria-hidden", "true");
    target.setAttribute("inert", "");
  }

  return () => {
    body.style.overflow = previousOverflow;
    for (const previous of previousAttributes) {
      restoreAttribute(previous.target, "aria-hidden", previous.ariaHidden);
      restoreAttribute(previous.target, "inert", previous.inert);
    }
  };
}

/** Returns the element that must receive focus to keep Tab inside the dialog. */
export function resolveOverlayTabTarget<T>(
  focusable: readonly T[],
  activeElement: T | null,
  backwards: boolean
): T | null | undefined {
  if (focusable.length === 0) {
    return null;
  }

  const activeIndex = activeElement === null ? -1 : focusable.indexOf(activeElement);
  if (backwards && activeIndex <= 0) {
    return focusable[focusable.length - 1];
  }
  if (!backwards && (activeIndex === -1 || activeIndex === focusable.length - 1)) {
    return focusable[0];
  }
  return undefined;
}

export function OverlayShell({
  backgroundRef,
  children,
  closeDisabled = false,
  closeLabel = "Закрыть",
  label,
  mode,
  onClose
}: OverlayShellProps) {
  const backdropRef = useRef<HTMLDivElement | null>(null);
  const dialogRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  const closeDisabledRef = useRef(closeDisabled);
  const openerRef = useRef<HTMLElement | null>(null);
  const reactId = useId();
  const titleId = `overlay-shell-title-${reactId.replaceAll(":", "")}`;

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    closeDisabledRef.current = closeDisabled;
  }, [closeDisabled]);

  useEffect(() => {
    const dialogElement = dialogRef.current;
    if (!dialogElement) {
      return;
    }
    const mountedDialog: HTMLElement = dialogElement;

    openerRef.current = asFocusableElement(document.activeElement);
    const backdropElement = backdropRef.current;
    const bodyBackgrounds =
      backdropElement?.parentElement === document.body
        ? Array.from(document.body.children).filter(
            (element) => element !== backdropElement
          )
        : [];
    const restoreEnvironment = lockOverlayEnvironment(
      bodyBackgrounds.length > 0 ? bodyBackgrounds : backgroundRef.current,
      document.body
    );

    const focusable = getFocusableElements(mountedDialog);
    (focusable[0] ?? mountedDialog).focus({ preventScroll: true });

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        if (!closeDisabledRef.current) {
          onCloseRef.current();
        }
        return;
      }
      if (event.key !== "Tab") {
        return;
      }

      const currentFocusable = getFocusableElements(mountedDialog);
      const activeElement = asFocusableElement(document.activeElement);
      const target = resolveOverlayTabTarget(
        currentFocusable,
        activeElement,
        event.shiftKey
      );
      if (target === undefined) {
        return;
      }

      event.preventDefault();
      (target ?? mountedDialog).focus({ preventScroll: true });
    }

    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      restoreEnvironment();
      const opener = openerRef.current;
      if (opener?.isConnected) {
        opener.focus({ preventScroll: true });
      }
    };
  }, [backgroundRef]);

  function onBackdropMouseDown(event: ReactMouseEvent<HTMLDivElement>) {
    if (event.target === event.currentTarget && !closeDisabledRef.current) {
      onCloseRef.current();
    }
  }

  const overlay = (
    // biome-ignore lint/a11y/noStaticElementInteractions: Mouse backdrop dismissal is redundant with the close button and Escape handling.
    <div
      className="overlay-shell-backdrop"
      data-mode={mode}
      onMouseDown={onBackdropMouseDown}
      ref={backdropRef}
    >
      <section
        aria-labelledby={titleId}
        aria-modal="true"
        className={`overlay-shell-dialog overlay-shell-dialog--${mode}`}
        ref={dialogRef}
        role="dialog"
        tabIndex={-1}
      >
        <header className="overlay-shell-header">
          <h2 id={titleId}>{label}</h2>
          <button
            aria-label={closeLabel}
            className="overlay-shell-close"
            disabled={closeDisabled}
            onClick={() => onCloseRef.current()}
            type="button"
          >
            <span aria-hidden="true">×</span>
          </button>
        </header>
        <div className="overlay-shell-content">{children}</div>
      </section>
    </div>
  );

  return typeof document === "undefined"
    ? overlay
    : createPortal(overlay, document.body);
}

function getFocusableElements(dialog: HTMLElement): HTMLElement[] {
  return Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).filter(
    (element) => {
      if (element.closest("[inert], [aria-hidden='true']")) {
        return false;
      }
      const style = window.getComputedStyle(element);
      return style.display !== "none" && style.visibility !== "hidden";
    }
  );
}

function asFocusableElement(value: Element | null): HTMLElement | null {
  return value instanceof HTMLElement ? value : null;
}

function restoreAttribute(
  target: AttributeTarget | null,
  name: string,
  previousValue: string | null
) {
  if (!target) {
    return;
  }
  if (previousValue === null) {
    target.removeAttribute(name);
    return;
  }
  target.setAttribute(name, previousValue);
}
