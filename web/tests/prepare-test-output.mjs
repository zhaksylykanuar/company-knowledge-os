import { mkdirSync, writeFileSync } from "node:fs";

mkdirSync(".tmp-test", { recursive: true });
writeFileSync(".tmp-test/package.json", '{"type":"commonjs"}\n');
