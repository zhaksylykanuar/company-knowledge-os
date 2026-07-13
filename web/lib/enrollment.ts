const CYRILLIC_TO_LATIN: Record<string, string> = {
  а: "a",
  б: "b",
  в: "v",
  г: "g",
  д: "d",
  е: "e",
  ё: "e",
  ж: "zh",
  з: "z",
  и: "i",
  й: "i",
  к: "k",
  л: "l",
  м: "m",
  н: "n",
  о: "o",
  п: "p",
  р: "r",
  с: "s",
  т: "t",
  у: "u",
  ф: "f",
  х: "h",
  ц: "c",
  ч: "ch",
  ш: "sh",
  щ: "shch",
  ъ: "",
  ы: "y",
  ь: "",
  э: "e",
  ю: "yu",
  я: "ya",
  ә: "a",
  ғ: "gh",
  қ: "q",
  ң: "n",
  ө: "o",
  ұ: "u",
  ү: "u",
  һ: "h",
  і: "i"
};

export function enrollmentTokenFromLocation(location: {
  hash: string;
  search: string;
}): string | null {
  // The bearer token lives in the URL fragment so it never reaches the Next.js
  // request line, proxy, access logs, or Referer header. Query-token fallback is
  // intentionally forbidden.
  const fragment = location.hash.startsWith("#")
    ? location.hash.slice(1)
    : location.hash;
  return new URLSearchParams(fragment).get("token");
}

export function setupTokenFromLocation(location: {
  hash: string;
  search: string;
}): string | null {
  // Teammate setup links follow the same fragment-only bearer contract. Never
  // restore the legacy query fallback: query strings reach HTTP/access logs.
  return enrollmentTokenFromLocation(location);
}

export function companyNameToSlug(value: string): string {
  return value
    .trim()
    .toLocaleLowerCase("ru")
    .split("")
    .map((character) => CYRILLIC_TO_LATIN[character] ?? character)
    .join("")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
}
