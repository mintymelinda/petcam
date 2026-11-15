const fs = require("node:fs");
const recast = require("recast");
const babelParser = require("@babel/parser");

const file = "src/petcam/static/dashboard.js";
const source = fs.readFileSync(file, "utf8");
const ast = recast.parse(source, {
  parser: {
    parse(input) {
      return babelParser.parse(input, {
        sourceType: "script",
        plugins: ["optionalChaining", "nullishCoalescingOperator"],
      });
    },
  },
});

const body = ast.program.body;
const declarations = body.filter((node) => node.type === "VariableDeclaration");
const functions = body.filter((node) => node.type === "FunctionDeclaration");
const initialization = body.filter(
  (node) =>
    node.type !== "VariableDeclaration" && node.type !== "FunctionDeclaration",
);

if (declarations.length === 0 || functions.length === 0 || initialization.length === 0) {
  throw new Error("Unexpected dashboard structure; refusing to rewrite the file.");
}

const b = recast.types.builders;
declarations[0].leadingComments = [
  ...(declarations[0].leadingComments || []),
  b.commentLine(" DOM references and shared state"),
];
functions[0].leadingComments = [
  ...(functions[0].leadingComments || []),
  b.commentLine(" Feature and API functions"),
];

const initialize = b.functionDeclaration(
  b.identifier("initializeDashboard"),
  [],
  b.blockStatement(initialization),
  false,
  false,
);
initialize.leadingComments = [
  b.commentLine(" Event bindings, initial data loads, and polling"),
];

ast.program.body = [
  ...declarations,
  ...functions,
  initialize,
  b.expressionStatement(
    b.callExpression(b.identifier("initializeDashboard"), []),
  ),
];

fs.writeFileSync(file, recast.print(ast).code + "\n");
