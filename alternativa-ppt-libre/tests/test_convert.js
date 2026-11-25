// tests/test_convert.js
// Markdown <-> PPTX XML round trips, slide / markdown editing, save & reload and package checks.
// Run: open tests/test_convert.html in the browser.

// The smallest usable file headers; the app stores images without decoding them.
const PNG_BYTES = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, ...new TextEncoder().encode('png-content')]);
const JPEG_BYTES = new Uint8Array([0xff, 0xd8, 0xff, ...new TextEncoder().encode('jpeg-content')]);

const SPEC_EXAMPLE = `## Chapter 1: AI Adoption Strategy

### Current Challenges

- Labor shortage
- Knowledge tied to individuals
- Underused data

### AI Adoption Policy

- Automate routine work
- Promote data use

## Chapter 2: Execution Plan

### Rollout Schedule

1. Planning
2. Pilot
3. Full rollout
`;

const NESTED = `### Levels

#### Subheading

First body line
Second body line

- Level 0
  - Level 1
    - Level 2
  - Level 1-2
1. Number
   1. Child number
   - Child bullet
2. Number 2
- Multi-line item
  Continued line
- \\- Starts with a hyphen
`;

const TITLED = `# Proposal

November 2026

## Chapter 1

### One

### Two

## Chapter 2

### Three
`;

const MIXED = `# Cover

Subtitle

## Chapter

Note

### Normal

#### Subheading

Body

- Item
  - Child
1. Number
`;

const DESIGN_MD = '# Cover\n\n## Chapter\n\n### One\n\n- a\n\n### Two\n\n- b\n';

// --- runner ---

const tests = [];

// Registers a test; its body may be async.
function test(name, body) {
  tests.push([name, body]);
}

// Readable form of a value in a failure message.
function shown(value) {
  return typeof value === 'string' ? value : JSON.stringify(value);
}

function assertEqual(actual, expected, label = '') {
  if (JSON.stringify(actual) !== JSON.stringify(expected)) {
    throw new Error(`${label ? `${label}: ` : ''}expected ${shown(expected)}\n  but got ${shown(actual)}`);
  }
}

function assertTrue(value, label = 'expected true') {
  if (!value) throw new Error(label);
}

function assertIncludes(text, part) {
  if (!text.includes(part)) throw new Error(`expected to find ${shown(part)}\n  in ${shown(text)}`);
}

function assertNotIncludes(items, item) {
  if (items.includes(item)) throw new Error(`did not expect ${shown(item)}`);
}

// Asserts that an async or plain call throws; the error class is checked when given.
async function assertThrows(call, errorClass = Error) {
  let thrown = null;
  try {
    await call();
  } catch (e) {
    thrown = e;
  }
  if (!thrown) throw new Error('expected an error');
  if (!(thrown instanceof errorClass)) throw new Error(`expected ${errorClass.name}, got ${thrown}`);
}

// --- helpers ---

// Semantic slide content straight from the slide XML of a deck.
function xmlStructure(deck) {
  return structureOf(readSlides(deck));
}

// Semantic slide content of a markdown text.
function mdStructure(md) {
  return structureOf(parseMarkdown(md));
}

// Titles of a deck's slides in order.
function titles(deck) {
  return readSlides(deck).map((s) => s.title);
}

// A package as a small reader: part names, text and parsed XML of a part.
async function openPackage(data) {
  const zip = await JSZip.loadAsync(data);
  const names = Object.keys(zip.files);
  const text = (name) => zip.file(name).async('string');
  return {
    zip,
    names,
    text,
    bytes: (name) => zip.file(name).async('uint8array'),
    xml: async (name) => parseXml(await text(name)),
  };
}

// A deck's built package as a small reader.
async function packageOf(deck) {
  return openPackage(await buildPptx(deck));
}

// A layout part of a built package, by slide kind.
function layoutOf(pack, kind) {
  return pack.xml(layoutPath(kind));
}

// Footer shapes of a slide part: placeholder type -> shape.
async function footerShapesOf(pack, part) {
  const shapes = {};
  descendantsOf(await pack.xml(part), 'p:sp').forEach((sp) => {
    const type = placeholderOf(sp).getAttribute('type');
    if ([FOOTER_DATE, FOOTER_TEXT, FOOTER_NUMBER].includes(type)) shapes[type] = sp;
  });
  return shapes;
}

// Slide parts of a built package, in presentation order.
async function slidePartsInOrder(pack) {
  const pres = await pack.xml('ppt/presentation.xml');
  const rels = parseRels(await pack.bytes('ppt/_rels/presentation.xml.rels'));
  return descendantsOf(pres, 'p:sldId').map((el) => `ppt/${rels[el.getAttributeNS(NS.r, 'id')][1]}`);
}

// Serialized text of a slide's XML.
function slideXmlText(deck, sid) {
  return new XMLSerializer().serializeToString(deck.slides.get(sid).xml);
}

// --- markdown -> slides ---

test('spec example makes five slides', () => {
  const slides = parseMarkdown(SPEC_EXAMPLE);
  assertEqual(slides.map((s) => [s.kind, s.title]), [
    [KIND_CHAPTER, 'Chapter 1: AI Adoption Strategy'], [KIND_NORMAL, 'Current Challenges'], [KIND_NORMAL, 'AI Adoption Policy'],
    [KIND_CHAPTER, 'Chapter 2: Execution Plan'], [KIND_NORMAL, 'Rollout Schedule'],
  ]);
  assertEqual(slides[4].blocks.map((b) => b.type), [BLOCK_NUMBER, BLOCK_NUMBER, BLOCK_NUMBER]);
});

test('chapter text is subtitle', () => {
  assertEqual(parseMarkdown('## Chapter\n\nA supporting line\n')[0].blocks, [{ type: BLOCK_PARA, level: 0, text: 'A supporting line' }]);
});

test('nesting and block types', () => {
  assertEqual(parseMarkdown(NESTED)[0].blocks.map((b) => [b.type, b.level, b.text]), [
    [BLOCK_HEADING, 0, 'Subheading'],
    [BLOCK_PARA, 0, 'First body line\nSecond body line'],
    [BLOCK_BULLET, 0, 'Level 0'], [BLOCK_BULLET, 1, 'Level 1'], [BLOCK_BULLET, 2, 'Level 2'],
    [BLOCK_BULLET, 1, 'Level 1-2'],
    [BLOCK_NUMBER, 0, 'Number'], [BLOCK_NUMBER, 1, 'Child number'], [BLOCK_BULLET, 1, 'Child bullet'],
    [BLOCK_NUMBER, 0, 'Number 2'],
    [BLOCK_BULLET, 0, 'Multi-line item\nContinued line'],
    // Only whole lines are unescaped; after a list marker the text is taken as written.
    [BLOCK_BULLET, 0, '\\- Starts with a hyphen'],
  ]);
});

test('separator is not a slide break', () => {
  assertEqual(parseMarkdown('### A\n\n---\n\n- x\n').length, 1);
});

test('tabs indent lists to columns of four', () => {
  assertEqual(parseMarkdown('### A\n\n- a\n\t- b\n')[0].blocks.map((b) => b.level), [0, 1]);
});

// --- round trips ---

test('markdown -> pptx -> markdown', async () => {
  for (const md of [SPEC_EXAMPLE, SAMPLE_MARKDOWN, NESTED]) {
    const deck = deckFromMarkdown(md);
    assertEqual(mdStructure(deckToMarkdown(deck)), mdStructure(md));
    const reloaded = await loadPptx(await buildPptx(deck));
    assertEqual(mdStructure(deckToMarkdown(reloaded)), mdStructure(md));
  }
});

test('canonical markdown is stable', () => {
  [SPEC_EXAMPLE, SAMPLE_MARKDOWN, NESTED].forEach((md) => {
    const canonical = slidesToMarkdown(parseMarkdown(md));
    assertEqual(slidesToMarkdown(parseMarkdown(canonical)), canonical);
  });
  assertEqual(slidesToMarkdown(parseMarkdown(SPEC_EXAMPLE)), SPEC_EXAMPLE);
});

test('pptx xml -> markdown -> pptx xml', async () => {
  const original = await loadPptx(await buildPptx(deckFromMarkdown(`${NESTED}\n${SAMPLE_MARKDOWN}`)));
  const rebuilt = await loadPptx(await buildPptx(deckFromMarkdown(deckToMarkdown(original))));
  assertEqual(xmlStructure(rebuilt), xmlStructure(original));
  assertEqual(rebuilt.order.length, original.order.length);
});

test('escapes survive', () => {
  const tricky = [{ kind: KIND_NORMAL, title: '# Symbols', blocks: [
    { type: BLOCK_PARA, level: 0, text: '# Not a heading\n- Not a bullet\n1. Not a number either\n---\n\\- Backslash' },
    { type: BLOCK_BULLET, level: 0, text: 'Item\n## Continued' },
    { type: BLOCK_BULLET, level: 0, text: '' },
    { type: BLOCK_HEADING, level: 0, text: '' },
  ] }];
  assertEqual(mdStructure(slidesToMarkdown(tricky)), structureOf(tricky));
});

test('Japanese text and order', async () => {
  const text = '日本語テキスト🎌「かぎ括弧」';
  const deck = await loadPptx(await buildPptx(deckFromMarkdown(`### First\n\n- ${text}\n\n### Second\n\n### Third\n`)));
  const slides = readSlides(deck);
  assertEqual(slides.map((s) => s.title), ['First', 'Second', 'Third']);
  assertEqual(slides[0].blocks[0].text, text);
});

test('XML special characters survive', async () => {
  const md = '### A & B <C> "D"\n\n- x < y && z > "w"\n';
  const deck = await loadPptx(await buildPptx(deckFromMarkdown(md)));
  assertEqual(deckToMarkdown(deck), md);
});

// --- markdown edits ---

test('typing keeps slide parts', () => {
  const session = new Session(SPEC_EXAMPLE);
  const ids = [...session.deck.order];
  const longer = '### Current Challenges and Background';
  for (let n = '### Current Challenges'.length; n <= longer.length; n += 1) {
    session.applyMarkdown(SPEC_EXAMPLE.replace('### Current Challenges', longer.slice(0, n)), 'md', n * 0.1);
  }
  assertEqual(session.deck.order, ids);
  assertEqual(readSlides(session.deck)[1].title, 'Current Challenges and Background');
  assertEqual(session.md, SPEC_EXAMPLE.replace('### Current Challenges', longer));
});

test('add, delete and reorder sections', () => {
  const session = new Session(SPEC_EXAMPLE);
  const ids = [...session.deck.order];
  const md = `${SPEC_EXAMPLE.replace('### AI Adoption Policy\n\n- Automate routine work\n- Promote data use\n\n', '')}\n### Summary\n\n- The end\n`;
  session.applyMarkdown(md);
  assertEqual(titles(session.deck), ['Chapter 1: AI Adoption Strategy', 'Current Challenges', 'Chapter 2: Execution Plan', 'Rollout Schedule', 'Summary']);
  assertNotIncludes(session.deck.order, ids[2]);
  // Swap the two chapters' sections: existing slide parts are moved, not recreated.
  const chapters = md.split('## Chapter 2');
  const before = [...session.deck.order].sort();
  session.applyMarkdown(`## Chapter 2${chapters[1].trimEnd()}\n\n${chapters[0]}`);
  assertEqual([...session.deck.order].sort(), before);
  assertEqual(readSlides(session.deck)[0].title, 'Chapter 2: Execution Plan');
});

test('no change when markdown is reapplied', () => {
  const deck = deckFromMarkdown(SAMPLE_MARKDOWN);
  assertEqual(applySlides(deck, parseMarkdown(deckToMarkdown(deck))), false);
});

test('heading level change switches kind', () => {
  const session = new Session(SPEC_EXAMPLE);
  const sid = session.deck.order[1];
  session.applyMarkdown(SPEC_EXAMPLE.replace('### Current Challenges', '## Current Challenges'));
  assertEqual(session.deck.order[1], sid);
  assertEqual(slideKind(session.deck, sid), KIND_CHAPTER);
});

// --- slide edits ---

test('set_slide updates markdown', () => {
  const session = new Session(SPEC_EXAMPLE);
  session.applyOp({ op: 'set_slide', id: session.deck.order[1], title: 'Challenges (updated)', blocks: [
    { type: BLOCK_BULLET, level: 0, text: 'Labor shortage' },
    { type: BLOCK_BULLET, level: 1, text: 'Hiring difficulty' },
    { type: BLOCK_NUMBER, level: 0, text: 'Countermeasures' },
  ] });
  assertIncludes(session.md, '### Challenges (updated)\n\n- Labor shortage\n  - Hiring difficulty\n1. Countermeasures\n');
  assertEqual(mdStructure(session.md), xmlStructure(session.deck));
});

test('insert, delete and kind change', () => {
  const session = new Session(SPEC_EXAMPLE);
  session.applyOp({ op: 'insert', id: session.deck.order[0], kind: KIND_NORMAL });
  assertEqual(readSlides(session.deck)[1].title, 'New Slide');
  assertIncludes(session.md, '## Chapter 1: AI Adoption Strategy\n\n### New Slide\n\n-\n');
  const newId = session.deck.order[1];
  session.applyOp({ op: 'set_kind', id: newId, kind: KIND_CHAPTER });
  assertIncludes(session.md, '\n## New Slide\n');
  session.applyOp({ op: 'delete', id: newId });
  assertEqual(mdStructure(session.md), mdStructure(SPEC_EXAMPLE));
  session.applyOp({ op: 'insert', id: null, kind: KIND_CHAPTER });
  assertTrue(session.md.startsWith('## New Chapter\n'));
});

test('move chapter with its slides', () => {
  const session = new Session(SPEC_EXAMPLE);
  session.applyOp({ op: 'move', id: session.deck.order[3], direction: -1 });
  assertEqual(titles(session.deck), ['Chapter 2: Execution Plan', 'Rollout Schedule', 'Chapter 1: AI Adoption Strategy', 'Current Challenges', 'AI Adoption Policy']);
  assertTrue(session.md.startsWith('## Chapter 2: Execution Plan\n\n### Rollout Schedule\n'));
  assertEqual(mdStructure(session.md), xmlStructure(session.deck));
});

test('move normal slide across a chapter', () => {
  const session = new Session(SPEC_EXAMPLE);
  const sid = session.deck.order[2];
  session.applyOp({ op: 'move', id: sid, direction: 1 });
  assertEqual(titles(session.deck).slice(2, 4), ['Chapter 2: Execution Plan', 'AI Adoption Policy']);
  // The moved slide keeps its own content.
  assertEqual(readSlide(session.deck, sid).blocks[0].text, 'Automate routine work');
});

test('slide edit round trip is idempotent', () => {
  // The markdown regenerated after a slide edit must not change the XML again (no sync loop).
  const session = new Session(NESTED);
  session.applyOp({ op: 'set_slide', id: session.deck.order[0], title: 'x', blocks: [{ type: BLOCK_PARA, text: 'y' }] });
  assertEqual(applySlides(session.deck, parseMarkdown(session.md)), false);
});

test('unknown slide is an error', async () => {
  await assertThrows(() => new Session(SPEC_EXAMPLE).applyOp({ op: 'delete', id: 99999 }));
});

// --- title slides ---

test('heading levels', () => {
  const slides = parseMarkdown('# Cover\n\nSubtitle\n\n## Chapter\n\n### Normal\n\n#### Subheading\n\n##### Deep heading\n');
  assertEqual(slides.map((s) => s.kind), [KIND_TITLE, KIND_CHAPTER, KIND_NORMAL]);
  assertEqual(slides[0].blocks, [{ type: BLOCK_PARA, level: 0, text: 'Subtitle' }]);
  assertEqual(slides[2].blocks.map((b) => [b.type, b.text]), [[BLOCK_HEADING, 'Subheading'], [BLOCK_HEADING, 'Deep heading']]);
});

test('title slides round trip through the package', async () => {
  const deck = await loadPptx(await buildPptx(deckFromMarkdown(TITLED)));
  assertEqual(deckToMarkdown(deck), TITLED);
  assertEqual(slideKind(deck, deck.order[0]), KIND_TITLE);
});

test('title slide uses the title layout and placeholders', () => {
  const deck = deckFromMarkdown(TITLED);
  const rec = deck.slides.get(deck.order[0]);
  assertTrue(layoutPartOf(rec).endsWith('slideLayout3.xml'));
  assertEqual(descendantsOf(rec.xml, 'p:ph').map((ph) => ph.getAttribute('type')), ['ctrTitle', 'subTitle']);
});

test('kind changes keep text', () => {
  const session = new Session(TITLED);
  const sid = session.deck.order[2];
  [[KIND_TITLE, '# One'], [KIND_CHAPTER, '## One'], [KIND_NORMAL, '### One']].forEach(([kind, mark]) => {
    session.applyOp({ op: 'set_kind', id: sid, kind });
    assertEqual(slideKind(session.deck, sid), kind);
    assertIncludes(session.md, `\n${mark}\n`);
    assertEqual(mdStructure(session.md), xmlStructure(session.deck));
  });
  assertEqual(descendantsOf(session.deck.slides.get(sid).xml, 'p:ph').map((ph) => ph.getAttribute('type')), ['title', null]);
});

test('insert title slide', () => {
  const session = new Session(TITLED);
  session.applyOp({ op: 'insert', id: session.deck.order[session.deck.order.length - 1], kind: KIND_TITLE });
  assertTrue(session.md.endsWith('\n# New Title\n'));
});

test('chapter move stops at the title slide', () => {
  const session = new Session(TITLED);
  const [, ch1, , , ch2] = session.deck.order;
  session.applyOp({ op: 'move', id: ch2, direction: -1 });
  assertEqual(titles(session.deck), ['Proposal', 'Chapter 2', 'Three', 'Chapter 1', 'One', 'Two']);
  session.applyOp({ op: 'move', id: ch2, direction: -1 });
  assertEqual(titles(session.deck), ['Chapter 2', 'Three', 'Proposal', 'Chapter 1', 'One', 'Two']);
  session.applyOp({ op: 'move', id: ch1, direction: -1 });
  assertEqual(titles(session.deck), ['Chapter 2', 'Three', 'Chapter 1', 'One', 'Two', 'Proposal']);
});

test('title slide moves alone', () => {
  const session = new Session(TITLED);
  const title = session.deck.order[0];
  session.applyOp({ op: 'move', id: title, direction: 1 });
  assertEqual(titles(session.deck), ['Chapter 1', 'One', 'Two', 'Proposal', 'Chapter 2', 'Three']);
  session.applyOp({ op: 'move', id: title, direction: -1 });
  assertEqual(titles(session.deck), ['Proposal', 'Chapter 1', 'One', 'Two', 'Chapter 2', 'Three']);
  assertEqual(moveSlide(session.deck, title, -1), false);
});

// --- layouts ---

test('three placements for every kind', () => {
  const { placements } = layoutCatalog();
  KINDS.forEach((kind) => assertEqual(placements[kind].map((p) => p.id), LAYOUT_PATTERNS));
});

test('placement is position only', () => {
  Object.values(SLIDE_LAYOUTS).forEach((patterns) => Object.values(patterns).forEach((spec) => assertTrue(!('title_color' in spec))));
});

test('every placement keeps the markdown', async () => {
  for (const kind of KINDS) {
    for (const pattern of LAYOUT_PATTERNS) {
      const choices = defaultLayouts();
      choices[kind][SLOT_SLIDE] = pattern;
      const deck = deckFromMarkdown(MIXED);
      setLayouts(deck, choices);
      assertEqual(deckToMarkdown(deck), MIXED);
      const reloaded = await loadPptx(await buildPptx(deck));
      assertEqual(deckToMarkdown(reloaded), MIXED);
      assertEqual(reloaded.layouts, choices);
    }
  }
});

test('text properties never change block types', async () => {
  for (const bold of [true, false]) {
    const props = { bold, italic: true, underline: true, font: 'Meiryo', color: 'ABCDEF', size: 2000 };
    const styles = {};
    KINDS.forEach((kind) => {
      styles[kind] = {};
      TEXT_SLOTS.forEach((slot) => { styles[kind][slot] = props; });
    });
    const deck = deckFromMarkdown(MIXED, undefined, styles);
    assertEqual(deckToMarkdown(deck), MIXED);
    const reloaded = await loadPptx(await buildPptx(deck));
    assertEqual(deckToMarkdown(reloaded), MIXED);
    assertEqual(reloaded.styles, normalizeStyles(styles));
  }
});

test('every choice keeps the markdown', async () => {
  const values = [
    ...FONT_CHOICES.map((f) => ['font', f]), ...FONT_SIZE_CHOICES.map((s) => ['size', s]),
    ...BULLET_CHOICES.map((c) => ['char', c]), ...Object.keys(NUMBER_SCHEMES).map((s) => ['scheme', s]),
  ];
  for (const [prop, value] of values) {
    const slot = { char: BLOCK_BULLET, scheme: BLOCK_NUMBER }[prop] || BLOCK_PARA;
    const deck = deckFromMarkdown(MIXED, undefined, { [KIND_NORMAL]: { [slot]: { [prop]: value } } });
    assertEqual(deckToMarkdown(await loadPptx(await buildPptx(deck))), MIXED, `${prop} ${value}`);
  }
});

test('properties reach the XML', async () => {
  const styles = { [KIND_NORMAL]: {
    [BLOCK_PARA]: { bold: true, italic: true, underline: true, font: 'Meiryo', color: 'abcdef', size: 2800 },
    [BLOCK_BULLET]: { char: '■' },
    [BLOCK_NUMBER]: { scheme: 'circleNumDbPlain' },
    [SLOT_TITLE]: { italic: true, font: 'Arial', color: '123456', size: 3600 },
  } };
  const choices = defaultLayouts();
  choices[KIND_NORMAL][SLOT_SLIDE] = 'c';
  const pack = await packageOf(deckFromMarkdown(MIXED, choices, styles));
  const slide = await pack.text('ppt/slides/slide3.xml');
  const layout = await pack.text('ppt/slideLayouts/slideLayout1.xml');
  assertTrue(/<a:rPr [^>]*sz="2800" b="1" i="1" u="sng"[^>]*><a:solidFill><a:srgbClr val="ABCDEF"\s*\/><\/a:solidFill><a:latin typeface="Meiryo"\s*\/><a:ea typeface="Meiryo"\s*\/>/.test(slide), slide);
  assertIncludes(slide, 'char="■"');
  assertIncludes(slide, 'type="circleNumDbPlain"');
  assertIncludes(layout, 'sz="3600" i="1"');
  assertIncludes(layout, '<a:srgbClr val="123456"/></a:solidFill><a:latin typeface="Arial"/>');
  const [x, y, cx, cy] = SLIDE_LAYOUTS[KIND_NORMAL].c.body_frame;
  assertIncludes(layout, `<a:off x="${x}" y="${y}"/><a:ext cx="${cx}" cy="${cy}"/>`);
});

test('size scales deeper levels', () => {
  const view = layoutView(defaultLayouts(), { [KIND_NORMAL]: { [BLOCK_BULLET]: { size: 3600 } } });
  assertEqual(view[KIND_NORMAL].types[BLOCK_BULLET].sizes.slice(0, 3), [3600, 3000, 2700]);
});

test('sizes round halves to even, as saved files always did', () => {
  assertEqual([0.5, 1.5, 2.5, 26.4, 26.6].map(roundHalfEven), [0, 2, 2, 26, 27]);
});

test('title size falls back to the placement', () => {
  const choices = defaultLayouts();
  assertEqual(layoutView(choices)[KIND_TITLE].title_size, SLIDE_LAYOUTS[KIND_TITLE].a.title_size);
  assertEqual(layoutView(choices, { [KIND_TITLE]: { [SLOT_TITLE]: { size: 7200 } } })[KIND_TITLE].title_size, 7200);
});

test('properties belong to their kind and type', () => {
  const styles = { [KIND_NORMAL]: { [BLOCK_PARA]: { italic: true } } };
  assertEqual(textStyle(styles, KIND_NORMAL, BLOCK_PARA).italic, true);
  assertEqual(textStyle(styles, KIND_CHAPTER, BLOCK_PARA).italic, false);
  assertEqual(textStyle(styles, KIND_NORMAL, BLOCK_HEADING).italic, false);
});

test('kind change follows its own properties', () => {
  const session = new Session('### Normal\n\nBody\n', undefined, { [KIND_CHAPTER]: { [BLOCK_PARA]: { size: 2000 } } });
  const sid = session.deck.order[0];
  session.applyOp({ op: 'set_kind', id: sid, kind: KIND_CHAPTER });
  assertIncludes(slideXmlText(session.deck, sid), 'sz="2000"');
});

test('layout change leaves markdown and history alone', () => {
  const session = new Session(MIXED);
  session.applyLayouts(defaultLayouts(), { [KIND_NORMAL]: { [BLOCK_HEADING]: { size: 3200 } } });
  assertEqual(session.md, MIXED);
  assertEqual(session.history.canUndo, false);
  assertEqual(session.state().layouts.view[KIND_NORMAL].types[BLOCK_HEADING].sizes[0], 3200);
  ensureInSync(session.deck, MIXED);
});

test('bad values are ignored', () => {
  assertEqual(normalizeLayouts({ [KIND_NORMAL]: { [SLOT_SLIDE]: 'z', [BLOCK_PARA]: 'c' }, y: {} }), defaultLayouts());
  assertEqual(normalizeStyles({
    [KIND_NORMAL]: {
      [BLOCK_PARA]: { font: 'No Such Font', color: 'red', bold: 'yes', size: 1234, char: '■', italic: true, x: 1 },
      [BLOCK_BULLET]: { char: 'x', scheme: 'arabicPeriod' },
    },
    y: {},
    [KIND_TITLE]: { z: { bold: true } },
  }), { [KIND_NORMAL]: { [BLOCK_PARA]: { italic: true } } });
});

// --- backgrounds and footers ---

test('nothing set keeps the white master background and no footer', async () => {
  const pack = await packageOf(deckFromMarkdown(DESIGN_MD));
  for (const kind of KINDS) assertEqual(findChild(await layoutOf(pack, kind), 'p:cSld', 'p:bg'), null);
  for (const part of await slidePartsInOrder(pack)) assertEqual(await footerShapesOf(pack, part), {});
});

test('background color is per kind on the layout', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_CHAPTER, { bg_color: '1f2937' });
  const pack = await packageOf(deck);
  const fill = findChild(await layoutOf(pack, KIND_CHAPTER), 'p:cSld', 'p:bg', 'p:bgPr', 'a:solidFill', 'a:srgbClr');
  assertEqual(fill.getAttribute('val'), '1F2937');
  assertEqual(findChild(await layoutOf(pack, KIND_NORMAL), 'p:cSld', 'p:bg'), null);
});

test('background image is embedded and survives reload', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  await setBackgroundImage(deck, KIND_NORMAL, PNG_BYTES);
  setDesign(deck, KIND_NORMAL, { bg_color: 'FF0000' });
  const name = deck.designs[KIND_NORMAL].bg_image;
  const data = await buildPptx(deck);
  const pack = await openPackage(data);
  assertEqual(Array.from(await pack.bytes(`ppt/media/${name}`)), Array.from(PNG_BYTES));
  const blip = findChild(await layoutOf(pack, KIND_NORMAL), 'p:cSld', 'p:bg', 'p:bgPr', 'a:blipFill', 'a:blip');
  const rels = parseRels(await pack.bytes('ppt/slideLayouts/_rels/slideLayout1.xml.rels'));
  assertEqual(rels[blip.getAttributeNS(NS.r, 'embed')][1], `../media/${name}`);
  assertIncludes(await pack.text('[Content_Types].xml'), '<Default Extension="png"');
  const loaded = await loadPptx(data);
  assertEqual(loaded.designs[KIND_NORMAL].bg_image, name);
  assertEqual(loaded.designs[KIND_NORMAL].bg_color, 'FF0000');
  assertEqual(Array.from(loaded.images[name]), Array.from(PNG_BYTES));
  assertIncludes((await packageOf(loaded)).names, `ppt/media/${name}`);
});

test('removed or replaced images leave the package', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  await setBackgroundImage(deck, KIND_NORMAL, PNG_BYTES);
  const first = deck.designs[KIND_NORMAL].bg_image;
  await setBackgroundImage(deck, KIND_NORMAL, JPEG_BYTES);
  const second = deck.designs[KIND_NORMAL].bg_image;
  assertTrue(second.endsWith('.jpg'));
  let pack = await packageOf(deck);
  assertNotIncludes(pack.names, `ppt/media/${first}`);
  assertIncludes(pack.names, `ppt/media/${second}`);
  setDesign(deck, KIND_NORMAL, { bg_image: null });
  pack = await packageOf(deck);
  assertEqual(pack.names.filter((n) => n.startsWith('ppt/media')), []);
  assertEqual(Object.keys(parseRels(await pack.bytes('ppt/slideLayouts/_rels/slideLayout1.xml.rels'))).length, 1);
});

test('the same image can serve two kinds', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  await setBackgroundImage(deck, KIND_NORMAL, PNG_BYTES);
  await setBackgroundImage(deck, KIND_TITLE, PNG_BYTES);
  setDesign(deck, KIND_NORMAL, { bg_image: null });
  assertEqual(Object.keys(deck.images), [deck.designs[KIND_TITLE].bg_image]);
});

test('only PNG and JPEG of usable size are taken', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  const encode = (text) => new TextEncoder().encode(text);
  for (const bad of [new Uint8Array(), encode('<svg></svg>'), encode('GIF89a')]) {
    await assertThrows(() => setBackgroundImage(deck, KIND_NORMAL, bad));
  }
  const tooLarge = new Uint8Array(MAX_IMAGE_BYTES + 1);
  tooLarge.set(PNG_BYTES);
  await assertThrows(() => setBackgroundImage(deck, KIND_NORMAL, tooLarge));
  assertEqual(deck.images, {});
});

test('image names are the same content hash as files saved earlier', async () => {
  // SHA-256 of "abc" is known; files saved by earlier versions name their images this way.
  const png = new Uint8Array([...IMAGE_SIGNATURES.png]);
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode('abc')));
  assertEqual(Array.from(digest.slice(0, 4), (b) => b.toString(16).padStart(2, '0')).join(''), 'ba7816bf');
  assertTrue(IMAGE_NAME_RE.test(await imageName(png)));
});

test('unknown design input is ignored', async () => {
  assertEqual(normalizeDesigns({
    nope: { bg_color: '000000' },
    [KIND_NORMAL]: { bg_color: 'red', bg_image: '../../secret.png', footer_text: 5, show_number: 'yes', x: 1 },
  }), defaultDesigns());
  await assertThrows(() => setDesign(newDeck(), 'nope', {}));
});

test('footers appear only on the chosen kind with correct numbers', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_NORMAL, { footer_text: 'A & B <Inc>', show_number: true, show_date: true });
  const pack = await packageOf(deck);
  const parts = await slidePartsInOrder(pack);
  assertEqual(await footerShapesOf(pack, parts[0]), {});
  assertEqual(await footerShapesOf(pack, parts[1]), {});
  const shapes = await footerShapesOf(pack, parts[3]);
  assertEqual(Object.keys(shapes).sort(), [FOOTER_DATE, FOOTER_TEXT, FOOTER_NUMBER].sort());
  assertEqual(descendantsOf(shapes[FOOTER_TEXT], 'a:t')[0].textContent, 'A & B <Inc>');
  const field = descendantsOf(shapes[FOOTER_NUMBER], 'a:fld')[0];
  assertEqual([field.getAttribute('type'), findChild(field, 'a:t').textContent], ['slidenum', '4']);
  assertEqual(descendantsOf(shapes[FOOTER_DATE], 'a:fld')[0].getAttribute('type'), 'datetime1');
  const ids = descendantsOf(await pack.xml(parts[3]), 'p:cNvPr').map((el) => el.getAttribute('id'));
  assertEqual(new Set(ids).size, ids.length);
});

test('footers never reach the markdown and survive reload', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_NORMAL, { footer_text: 'Confidential', show_number: true });
  const before = deckToMarkdown(deck);
  const data = await buildPptx(deck);
  assertEqual(deckToMarkdown(deck), before);
  const loaded = await loadPptx(data);
  assertEqual(deckToMarkdown(loaded), before);
  assertEqual(loaded.designs[KIND_NORMAL].footer_text, 'Confidential');
  await buildPptx(loaded);
  const pack = await packageOf(loaded);
  const parts = await slidePartsInOrder(pack);
  assertEqual(Object.keys(await footerShapesOf(pack, parts[2])).sort(), [FOOTER_TEXT, FOOTER_NUMBER].sort());
});

test('turning a footer off and moving a slide update the shapes', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_NORMAL, { footer_text: 'Confidential', show_number: true });
  await packageOf(deck);
  moveSlide(deck, deck.order[2], 1);
  let pack = await packageOf(deck);
  const parts = await slidePartsInOrder(pack);
  const number = (await footerShapesOf(pack, parts[3]))[FOOTER_NUMBER];
  assertEqual(findChild(descendantsOf(number, 'a:fld')[0], 'a:t').textContent, '4');
  setDesign(deck, KIND_NORMAL, { footer_text: '', show_number: false });
  pack = await packageOf(deck);
  assertEqual(await footerShapesOf(pack, parts[3]), {});
});

test('new slide and kind change follow the footer settings', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_CHAPTER, { footer_text: 'Chapter footer' });
  setSlideKind(deck, deck.order[2], KIND_CHAPTER);
  const newId = addSlide(deck, KIND_CHAPTER, deck.order.length);
  const pack = await packageOf(deck);
  const parts = await slidePartsInOrder(pack);
  assertEqual(deck.order.indexOf(newId), 4);
  assertTrue(FOOTER_TEXT in await footerShapesOf(pack, parts[2]));
  assertTrue(FOOTER_TEXT in await footerShapesOf(pack, parts[4]));
  assertEqual(await footerShapesOf(pack, parts[3]), {});
});

test('footer text properties are written to the runs', async () => {
  const deck = deckFromMarkdown(DESIGN_MD);
  setDesign(deck, KIND_NORMAL, { footer_text: 'Styled' });
  setLayouts(deck, deck.layouts, { [KIND_NORMAL]: { footer: { color: 'FFFFFF', bold: true, size: 1600 } } });
  assertEqual(deck.designs[KIND_NORMAL].footer_text, 'Styled');
  const pack = await packageOf(deck);
  const sp = (await footerShapesOf(pack, (await slidePartsInOrder(pack))[2]))[FOOTER_TEXT];
  const props = findChild(descendantsOf(sp, 'a:r')[0], 'a:rPr');
  assertEqual([props.getAttribute('b'), props.getAttribute('sz')], ['1', '1600']);
  assertEqual(findChild(props, 'a:solidFill', 'a:srgbClr').getAttribute('val'), 'FFFFFF');
});

test('design changes leave markdown and history alone', async () => {
  const session = new Session(DESIGN_MD);
  session.applyMarkdown(`${DESIGN_MD}\n### Three\n`);
  const { md } = session;
  const { index } = session.history;
  session.applyDesign(KIND_NORMAL, { bg_color: '000000', footer_text: 'x' });
  await session.applyBackgroundImage(KIND_TITLE, JPEG_BYTES);
  assertEqual([session.md, session.history.index], [md, index]);
  session.undo();
  assertEqual(session.deck.designs[KIND_NORMAL].bg_color, '000000');
});

// --- undo / redo ---

test('typing merges and undo restores', async () => {
  const session = new Session('### A\n');
  session.applyMarkdown('### AB\n', 'md', 10.0);
  session.applyMarkdown('### ABC\n', 'md', 10.5);  // merged with the previous keystroke
  session.applyOp({ op: 'insert', id: session.deck.order[0], kind: KIND_NORMAL }, 11.0);
  session.undo();
  assertEqual(session.md, '### ABC\n');
  assertEqual(session.deck.order.length, 1);
  session.undo();
  assertEqual(session.md, '### A\n');
  assertEqual(readSlides(session.deck)[0].title, 'A');
  session.redo();
  assertEqual(readSlides(session.deck)[0].title, 'ABC');
  await assertThrows(() => { session.redo(); session.redo(); }, UserError);
});

// --- save and reload ---

test('reload and keep editing', async () => {
  const session = new Session(SPEC_EXAMPLE);
  const deck = await loadPptx(await buildPptx(session.deck));
  const second = new Session();
  second.reset(deck, deckToMarkdown(deck));
  assertEqual(mdStructure(second.md), mdStructure(SPEC_EXAMPLE));
  const sid = second.deck.order[second.deck.order.length - 1];
  second.applyOp({ op: 'set_slide', id: sid, title: 'Edited after reload', blocks: [] });
  second.applyMarkdown(`${second.md}\n### Added\n`);
  const again = await loadPptx(await buildPptx(second.deck));
  assertEqual(titles(again).slice(-2), ['Edited after reload', 'Added']);
});

test('out of sync is refused', async () => {
  const session = new Session(SPEC_EXAMPLE);
  ensureInSync(session.deck, session.md);
  await assertThrows(() => ensureInSync(session.deck, `${session.md}\n### Not synced\n`), UserError);
  await assertThrows(() => exportFile(session, 'pptx', '### Different\n'), UserError);
  await assertThrows(() => exportFile(session, 'md', '### Different\n'), UserError);
});

test('saved files carry the current content', async () => {
  const session = new Session(SPEC_EXAMPLE);
  assertEqual(await (await exportFile(session, 'md', session.md)).text(), SPEC_EXAMPLE);
  const pptx = await exportFile(session, 'pptx', session.md);
  assertEqual(pptx.type, CT_PPTX);
  const deck = await loadPptx(new Uint8Array(await pptx.arrayBuffer()));
  assertEqual(deckToMarkdown(deck), SPEC_EXAMPLE);
});

test('foreign or broken file is refused', async () => {
  await assertThrows(() => loadPptx(new TextEncoder().encode('not a zip')));
  const foreign = new JSZip();
  foreign.file('[Content_Types].xml', `<Types xmlns="${NS.ct}"/>`);
  foreign.file('_rels/.rels', `<Relationships xmlns="${NS.rel}"/>`);
  foreign.file('docProps/app.xml', `<Properties xmlns="${NS.app}"><Application>Microsoft Office PowerPoint</Application></Properties>`);
  await assertThrows(async () => loadPptx(await foreign.generateAsync({ type: 'uint8array' })), UserError);
});

// --- browser storage ---

// Pages opened from files share their storage; what the app keeps must stay out of reach here.
const TEST_DB = `${STORAGE_DB}-tests`;

test('work and settings are kept for the next visit', async () => {
  const session = new Session(DESIGN_MD);
  await session.applyBackgroundImage(KIND_TITLE, PNG_BYTES);
  session.applyDesign(KIND_NORMAL, { footer_text: 'Saved', bg_color: 'ABCDEF' });
  const choices = defaultLayouts();
  choices[KIND_TITLE][SLOT_SLIDE] = 'b';
  session.applyLayouts(choices, { [KIND_NORMAL]: { [BLOCK_PARA]: { bold: true } } });
  const { db } = await openSession(TEST_DB);
  await saveSettings(db, session.deck);
  await saveDraft(db, DESIGN_MD);
  const { session: next, storageError } = await openSession(TEST_DB);
  assertEqual(storageError, null);
  assertEqual(next.md, DESIGN_MD);
  assertEqual(next.deck.layouts, choices);
  assertEqual(next.deck.styles, session.deck.styles);
  assertEqual(next.deck.designs, session.deck.designs);
  const name = next.deck.designs[KIND_TITLE].bg_image;
  assertEqual(Array.from(next.deck.images[name]), Array.from(PNG_BYTES));
  assertIncludes((await packageOf(next.deck)).names, `ppt/media/${name}`);
  const st = next.state();
  assertEqual(Object.keys(st.images), [name]);
  assertEqual(st.layouts.view[KIND_TITLE].design.bg_image, name);
  session.applyDesign(KIND_TITLE, { bg_image: null });
  await saveSettings(db, session.deck);
  assertEqual((await openSession(TEST_DB)).session.deck.images, {});
});

test('an empty kept draft stays empty', async () => {
  const { db } = await openSession(TEST_DB);
  await saveDraft(db, '');
  assertEqual((await openSession(TEST_DB)).session.md, '');
});

test('saving without storage fails instead of writing elsewhere', async () => {
  await assertThrows(() => saveDraft(null, 'text'));
  await assertThrows(() => saveSettings(null, new Session().deck));
});

test('background URLs are filled in by image name', () => {
  const session = new Session(DESIGN_MD);
  session.applyDesign(KIND_TITLE, { bg_color: '123456' });
  const layouts = session.state().layouts;
  const named = { ...layouts, view: { ...layouts.view, [KIND_TITLE]: { ...layouts.view[KIND_TITLE], design: { ...layouts.view[KIND_TITLE].design, bg_image: 'bg_x.png' } } } };
  const filled = withBackgroundUrls(named, { 'bg_x.png': 'blob:x' });
  assertEqual(filled.view[KIND_TITLE].bg_url, 'blob:x');
  assertEqual(filled.view[KIND_NORMAL].bg_url, null);
  assertEqual(backgroundCss(filled.view[KIND_TITLE]).backgroundImage, 'url("blob:x")');
  assertEqual(named.view[KIND_TITLE].bg_url, undefined);
  assertEqual(imageBlob('bg_x.png', PNG_BYTES).type, 'image/png');
});

test('kept keys are reused by position, then new ones are made', () => {
  let n = 0;
  const next = keysFrom({ blocks: [{ key: 'a' }, { key: 'b' }] }, () => `n${++n}`);
  assertEqual([next(), next(), next()], ['a', 'b', 'n1']);
  assertEqual(keysFrom(null, () => 'z')(), 'z');
});

test('nothing kept starts with the sample', async () => {
  await storageRequest((await openSession(TEST_DB)).db, 'readwrite', (store) => store.clear());
  const { session } = await openSession(TEST_DB);
  assertEqual(session.md, SAMPLE_MARKDOWN);
  assertEqual(session.deck.layouts, defaultLayouts());
});

// --- generation API ---

// Runs body with fetch answering every call through answer(url, init); the real fetch comes back after.
async function withFetch(answer, body) {
  const realFetch = window.fetch;
  const calls = [];
  window.fetch = async (url, init) => { calls.push({ url, init }); return answer(url, init); };
  try {
    await body();
  } finally {
    window.fetch = realFetch;
  }
  return calls;
}

const jsonResponse = (status, data) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });

test('generated markdown is read into the app form', async () => {
  const calls = await withFetch(() => jsonResponse(200, { markdown: '# Deck\r\n### Slide\r\n- one' }), async () => {
    assertEqual(await generateMarkdown(GENERATE_NEW, 'make a deck', '# Old\n', null), '# Deck\n\n### Slide\n\n- one\n');
  });
  assertEqual(calls.length, 1);
  assertEqual(calls[0].url, `${API_BASE}/api/generate`);
  assertEqual(JSON.parse(calls[0].init.body), { request: 'make a deck', current: null });
});

test('revising sends the current markdown', async () => {
  const calls = await withFetch(() => jsonResponse(200, { markdown: '# Old\n\n### Added\n' }), async () => {
    assertEqual(await generateMarkdown(GENERATE_REVISE, 'add a slide', '# Old\n', null), '# Old\n\n### Added\n');
  });
  assertEqual(JSON.parse(calls[0].init.body), { request: 'add a slide', current: '# Old\n' });
});

test('generation errors say what went wrong', async () => {
  await withFetch(() => jsonResponse(502, { detail: 'Codex generation failed: x' }), async () => {
    let message = '';
    try { await generateMarkdown(GENERATE_NEW, 'x', '', null); } catch (e) { message = e.message; }
    assertEqual(message, 'Codex generation failed: x');
  });
  await withFetch(() => { throw new TypeError('Failed to fetch'); }, async () => {
    await assertThrows(() => generateMarkdown(GENERATE_NEW, 'x', '', null), ApiUnreachableError);
    assertEqual(await apiAvailable(), false);
  });
  await withFetch(() => jsonResponse(200, { markdown: '\n\n' }), async () => {
    await assertThrows(() => generateMarkdown(GENERATE_NEW, 'x', '', null), UserError);
  });
  const calls = await withFetch(() => jsonResponse(200, {}), async () => {
    await assertThrows(() => generateMarkdown(GENERATE_NEW, '  ', '', null), UserError);
    await assertThrows(() => generateMarkdown(GENERATE_REVISE, 'x', '\n', null), UserError);
  });
  assertEqual(calls.length, 0);
});

test('only this app counts as the API', async () => {
  await withFetch(() => jsonResponse(200, { name: API_NAME, path: 'x' }), async () => assertTrue(await apiAvailable()));
  await withFetch(() => jsonResponse(200, { name: 'other-app', path: 'x' }), async () => assertEqual(await apiAvailable(), false));
});

test('a generated deck is one undo step and keeps the layout settings', () => {
  const session = new Session('# Old\n');
  session.applyDesign(KIND_NORMAL, { footer_text: 'Kept' });
  session.applyMarkdown('# Old\n\nSub\n', 'md', 100);
  session.applyMarkdown(canonicalMarkdown('# New\n### A\n'), null, 100.1);
  assertEqual(session.md, '# New\n\n### A\n');
  assertEqual(session.deck.designs[KIND_NORMAL].footer_text, 'Kept');
  session.undo();
  assertEqual(session.md, '# Old\n\nSub\n');
});

// --- package validity ---

// A package with both nesting and every slide kind.
async function validityPackage() {
  return packageOf(deckFromMarkdown(`${NESTED}\n${SAMPLE_MARKDOWN}`));
}

test('every part is well-formed UTF-8 XML', async () => {
  const pack = await validityPackage();
  for (const name of pack.names) {
    const raw = await pack.text(name);
    assertTrue(raw.startsWith('<?xml version="1.0" encoding="UTF-8"'), name);
    parseXml(raw);
  }
});

test('no folder entries in the package', async () => {
  const pack = await validityPackage();
  assertEqual(pack.names.filter((name) => name.endsWith('/')), []);
  assertEqual(pack.names.slice(0, 2), [CONTENT_TYPES_PART, ROOT_RELS_PART]);
});

test('content types cover the parts', async () => {
  const pack = await validityPackage();
  const types = await pack.xml(CONTENT_TYPES_PART);
  const overrides = childrenOf(types, 'ct:Override').map((el) => el.getAttribute('PartName'));
  const defaults = childrenOf(types, 'ct:Default').map((el) => el.getAttribute('Extension'));
  pack.names.filter((name) => name !== CONTENT_TYPES_PART).forEach((name) => {
    assertTrue(overrides.includes(`/${name}`) || defaults.includes(name.split('.').pop()), name);
  });
  overrides.forEach((part) => assertIncludes(pack.names, part.replace(/^\//, '')));
});

test('relationship targets exist', async () => {
  const pack = await validityPackage();
  for (const name of pack.names.filter((n) => n.endsWith('.rels'))) {
    const source = dirName(dirName(name));
    Object.values(parseRels(await pack.bytes(name))).forEach(([, target]) => {
      assertIncludes(pack.names, resolvePart(`${source}/x`, target));
    });
  }
});

test('16:9 and native text', async () => {
  const pack = await validityPackage();
  const pres = await pack.xml(PRESENTATION_PART);
  const size = findChild(pres, 'p:sldSz');
  assertEqual([Number(size.getAttribute('cx')), Number(size.getAttribute('cy'))], [SLIDE_W, SLIDE_H]);
  assertEqual(SLIDE_W * 9, SLIDE_H * 16);
  const slide = await pack.text('ppt/slides/slide1.xml');
  assertIncludes(slide, 'Subheading');
  assertTrue(!slide.includes('p:pic'));
  assertEqual(pack.names.filter((n) => n.startsWith('ppt/media')), []);
  const ids = descendantsOf(pres, 'p:sldId').map((el) => Number(el.getAttribute('id')));
  assertEqual(new Set(ids).size, ids.length);
  assertTrue(ids.every((id) => id >= 256 && id < 2147483648));
});

// --- run ---

(async () => {
  const results = document.getElementById('results');
  const failures = [];
  for (const [name, body] of tests) {
    const line = document.createElement('div');
    try {
      await body();
      line.className = 'pass';
      line.textContent = `ok    ${name}`;
    } catch (e) {
      failures.push(name);
      line.className = 'fail';
      line.textContent = `FAIL  ${name}\n  ${e.message}`;
    }
    results.appendChild(line);
  }
  // Leave nothing of the tests in this browser's storage.
  await storageRequest((await openSession(TEST_DB)).db, 'readwrite', (store) => store.clear());
  document.getElementById('summary').textContent = `${tests.length - failures.length} of ${tests.length} passed`;
  window.testSummary = { total: tests.length, failures };
})();
