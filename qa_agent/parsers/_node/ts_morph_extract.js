#!/usr/bin/env node
/**
 * ts_morph_extract — read TS/JS files and emit a JSON ParsedFile array.
 *
 * Invoked by qa_agent.parsers.ts_morph_bridge as a subprocess.
 *
 * Input  (stdin, line-delimited JSON):  { "root": "<absolute>", "paths": ["src/a.ts", ...] }
 * Output (stdout, single JSON object):  { "files": [ParsedFile, ...] }
 *
 * Falls back to a tolerant regex extractor when ts-morph isn't installed,
 * so the QA Agent never hard-requires a Node dep — it just gets richer
 * data when one is available.
 */

"use strict";

const fs = require("fs");
const path = require("path");

const ROUTE_HINTS = ["get", "post", "put", "patch", "delete", "all", "use", "route", "router"];

function emit(obj) {
  process.stdout.write(JSON.stringify(obj));
}

function readStdin() {
  return new Promise((resolve, reject) => {
    let data = "";
    process.stdin.setEncoding("utf-8");
    process.stdin.on("data", (chunk) => (data += chunk));
    process.stdin.on("end", () => resolve(data));
    process.stdin.on("error", reject);
  });
}

function regexParse(abs, rel) {
  const out = { path: rel, language: rel.endsWith(".tsx") || rel.endsWith(".ts") ? "typescript" : "javascript", imports: [], symbols: [], routes: [] };
  let text;
  try {
    text = fs.readFileSync(abs, "utf-8");
  } catch (e) {
    out.parse_error = `read failed: ${e.message}`;
    return out;
  }
  const importRe = /^\s*import\s+(?:[^'"]+from\s+)?["']([^"']+)["']/gm;
  let m;
  while ((m = importRe.exec(text)) !== null) out.imports.push(m[1]);

  const funcRe = /^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z0-9_]+)\s*\(/gm;
  while ((m = funcRe.exec(text)) !== null) {
    out.symbols.push({ name: m[1], kind: "function", line: text.slice(0, m.index).split("\n").length });
  }
  const classRe = /^\s*(?:export\s+)?(?:abstract\s+)?class\s+([A-Za-z0-9_]+)/gm;
  while ((m = classRe.exec(text)) !== null) {
    out.symbols.push({ name: m[1], kind: "class", line: text.slice(0, m.index).split("\n").length });
  }
  const arrowRe = /^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z0-9_]+)\s*(?::\s*[^=]+)?=\s*(?:async\s*)?\(.*?\)\s*=>/gm;
  while ((m = arrowRe.exec(text)) !== null) {
    out.symbols.push({ name: m[1], kind: "function", line: text.slice(0, m.index).split("\n").length });
  }

  const routeRe = /(?:app|router|server)\s*\.\s*(get|post|put|patch|delete|all|use|route)\s*\(\s*["'`]([^"'`]+)["'`]/gi;
  while ((m = routeRe.exec(text)) !== null) {
    out.routes.push({
      name: `${m[1].toUpperCase()} ${m[2]}`,
      kind: "route",
      line: text.slice(0, m.index).split("\n").length,
    });
  }

  return out;
}

(async () => {
  const raw = await readStdin();
  let req;
  try {
    req = JSON.parse(raw);
  } catch (e) {
    emit({ error: `bad input: ${e.message}` });
    return;
  }
  const root = req.root;
  const paths = req.paths || [];

  // Prefer ts-morph if available; otherwise regex.
  let useTsMorph = false;
  let Project;
  try {
    ({ Project } = require("ts-morph"));
    useTsMorph = true;
  } catch (_e) {
    useTsMorph = false;
  }

  const files = [];
  if (useTsMorph) {
    const project = new Project({ skipAddingFilesFromTsConfig: true, useInMemoryFileSystem: false });
    for (const rel of paths) {
      const abs = path.join(root, rel);
      try {
        const sf = project.addSourceFileAtPath(abs);
        const out = { path: rel, language: rel.match(/\.tsx?$/) ? "typescript" : "javascript", imports: [], symbols: [], routes: [] };
        for (const imp of sf.getImportDeclarations()) {
          out.imports.push(imp.getModuleSpecifierValue());
        }
        for (const fn of sf.getFunctions()) {
          out.symbols.push({ name: fn.getName() || "<anonymous>", kind: "function", line: fn.getStartLineNumber() });
        }
        for (const cls of sf.getClasses()) {
          out.symbols.push({ name: cls.getName() || "<anonymous>", kind: "class", line: cls.getStartLineNumber() });
          for (const m of cls.getMethods()) {
            out.symbols.push({ name: m.getName(), kind: "method", line: m.getStartLineNumber(), parent: cls.getName() });
          }
        }
        for (const vs of sf.getVariableStatements()) {
          for (const decl of vs.getDeclarations()) {
            const init = decl.getInitializer();
            if (init && (init.getKindName() === "ArrowFunction" || init.getKindName() === "FunctionExpression")) {
              out.symbols.push({ name: decl.getName(), kind: "function", line: decl.getStartLineNumber() });
            }
          }
        }
        // Route hints: walk CallExpressions
        sf.forEachDescendant((node) => {
          if (node.getKindName() !== "CallExpression") return;
          const expr = node.getExpression();
          if (!expr || expr.getKindName() !== "PropertyAccessExpression") return;
          const prop = expr.getName ? expr.getName().toLowerCase() : "";
          if (!ROUTE_HINTS.includes(prop)) return;
          const args = node.getArguments();
          if (!args.length) return;
          const a0 = args[0];
          if (a0.getKindName() !== "StringLiteral" && a0.getKindName() !== "NoSubstitutionTemplateLiteral") return;
          const route = a0.getLiteralValue ? a0.getLiteralValue() : a0.getText().replace(/^['"`]|['"`]$/g, "");
          out.routes.push({
            name: `${prop.toUpperCase()} ${route}`,
            kind: "route",
            line: node.getStartLineNumber(),
          });
        });
        files.push(out);
      } catch (e) {
        files.push({ path: rel, language: "typescript", imports: [], symbols: [], routes: [], parse_error: String(e.message || e) });
      }
    }
  } else {
    for (const rel of paths) {
      files.push(regexParse(path.join(root, rel), rel));
    }
  }

  emit({ engine: useTsMorph ? "ts-morph" : "regex", files });
})();
