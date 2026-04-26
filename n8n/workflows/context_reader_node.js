// ============================================================
// FinBuddy Context Reader — N8N Code Node (v4 workflow)
// Place this node BEFORE the Groq HTTP Request node.
// Node type: Code | Language: JavaScript | Mode: Run Once For All Items
// ============================================================

const fs = require('fs');

const CONTEXT_FILE = '/data/finbuddy_memory/CONTEXT.md';
const RESEARCH_DIR = '/data/finbuddy_memory/research';

// --- Read CONTEXT.md ---
let contextContent = '';
try {
  contextContent = fs.readFileSync(CONTEXT_FILE, 'utf8');
  // Strip obsidian wikilinks for clean AI input
  contextContent = contextContent.replace(/\[\[.*?\]\]/g, '').trim();
} catch (e) {
  contextContent = '[FinBuddy memory not available]';
}

// --- Read last 3 days of research ---
let recentResearch = '';
try {
  const files = fs.readdirSync(RESEARCH_DIR)
    .filter(f => f.match(/^\d{4}-\d{2}-\d{2}\.md$/))
    .sort()
    .slice(-3); // last 3 days

  for (const file of files) {
    const content = fs.readFileSync(`${RESEARCH_DIR}/${file}`, 'utf8');
    // Strip wikilinks and trim
    recentResearch += content.replace(/\[\[.*?\]\]/g, '').trim() + '\n\n';
  }
} catch (e) {
  recentResearch = '[No recent research available]';
}

// --- Build the memory block to inject into Groq prompt ---
const memoryBlock = `
=== FinBuddy Memory ===
${contextContent}

=== Recent Research (last 3 days) ===
${recentResearch.trim()}
======================
`.trim();

// --- Pass forward with memory injected ---
// This merges memory into the existing item data
const items = $input.all();
return items.map(item => ({
  json: {
    ...item.json,
    finbuddy_memory: memoryBlock
  }
}));
