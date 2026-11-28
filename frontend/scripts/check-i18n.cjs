// Vérifier que chaque libellé utilisé dispose des trois traductions.
const fs = require('fs');
const ts = require('typescript');
const path = require('path');
const root = path.resolve(__dirname, '../src');
const messages = require('../src/translations.json');
const assert = require('node:assert/strict');
for (const [key, entry] of Object.entries(messages)) {
  for (const language of ['en', 'es', 'ar']) assert(entry[language]?.trim(), `${key}: ${language}`);
}
function inspect(file) {
  const src = ts.createSourceFile(file, fs.readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  function visit(node) {
    if (ts.isCallExpression(node) && node.expression.getText(src) === 't' && ts.isStringLiteral(node.arguments[0])) {
      assert(messages[node.arguments[0].text], `Traduction absente: ${node.arguments[0].text}`);
    }
    ts.forEachChild(node, visit);
  }
  visit(src);
}
for (const file of ['App.tsx','components/OCRPanel.tsx','components/DeleteDialog.tsx','components/ManageDialog.tsx','components/ImportDialog.tsx','components/SourceViewer.tsx','components/SearchAssessment.tsx']) inspect(path.join(root,file));
console.log(`${Object.keys(messages).length} libellés vérifiés en anglais, espagnol et arabe.`);
