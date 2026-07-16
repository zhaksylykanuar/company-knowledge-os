import { existsSync, mkdirSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

mkdirSync(".tmp-test", { recursive: true });
writeFileSync(".tmp-test/package.json", '{"type":"commonjs"}\n');

// TypeScript does not delete output for source tests that were renamed or
// removed. Drop only those stale compiled tests before Node discovers them.
for (const entry of readdirSync(".tmp-test/tests", { withFileTypes: true })) {
  if (!entry.isFile() || !entry.name.endsWith(".test.js")) {
    continue;
  }
  const sourceBase = entry.name.replace(/\.js$/, "");
  if (
    !existsSync(join("tests", `${sourceBase}.ts`)) &&
    !existsSync(join("tests", `${sourceBase}.tsx`))
  ) {
    rmSync(join(".tmp-test/tests", entry.name));
  }
}

// TypeScript resolves CSS module declarations but does not copy the files into
// the CommonJS test output. Small class-name stubs let Node load components
// without introducing a browser/CSS runtime into the focused unit tests.
for (const root of ["app", "components"]) {
  for (const entry of readdirSync(root, { recursive: true, withFileTypes: true })) {
    if (!entry.isFile() || !entry.name.endsWith(".module.css")) {
      continue;
    }
    const sourcePath = join(entry.parentPath, entry.name);
    const outputPath = join(".tmp-test", sourcePath);
    mkdirSync(dirname(outputPath), { recursive: true });
    writeFileSync(
      outputPath,
      [
        "const classes = new Proxy({}, { get: (target, property) => Reflect.has(target, property) ? Reflect.get(target, property) : String(property) });",
        'Object.defineProperty(classes, "__esModule", { value: true });',
        'Object.defineProperty(classes, "default", { value: classes });',
        "module.exports = classes;",
        ""
      ].join("\n")
    );
  }
}
