// common.js
// Markdown <-> PPTX (OOXML) conversion, in-memory deck editing, undo history, browser storage and
// the helpers index.html uses (highlighting, cursor mapping, slide-block editing).
// Definitions (templates, limits, lookup tables) are in data.js.
//
// The deck keeps the PPTX parts as XML in memory. Markdown edits are parsed and written into the
// slide XML; slide edits change the XML and the markdown is regenerated from it.
// DOMParser and XMLSerializer work on those XML documents only; the page itself is never touched.

// A precondition of the request isn't met (e.g. nothing to undo).
class UserError extends Error {}

// --- text ---

// Control characters XML 1.0 can't hold (tab and newline are handled separately).
const CONTROL_RE = /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/g;

// One line of slide text: control characters dropped, tabs as spaces, outer spaces trimmed.
function cleanLine(text) {
  return text.replace(/\t/g, ' ').replace(CONTROL_RE, '').trim();
}

// Text with every line ending as "\n".
function normalizeNewlines(text) {
  return text.replace(/\r\n/g, '\n').replace(/\r/g, '\n');
}

// Multi-line block text: each line cleaned, empty lines dropped.
function cleanText(text) {
  return normalizeNewlines(text).split('\n').map(cleanLine).filter(Boolean).join('\n');
}

// Whether a value is an object with named properties.
function isRecord(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

// Brings blocks into the shape markdown can express: known types, list levels at most one
// deeper than the list item before, single-line headings, no empty paragraphs.
function normalizeBlocks(blocks) {
  const result = [];
  let prevLevel = -1;  // level of the previous list item, -1 when the previous block isn't one
  blocks.forEach((block) => {
    const type = BLOCK_TYPES.includes(block.type) ? block.type : BLOCK_PARA;
    let text = cleanText(String(block.text || ''));
    let level = 0;
    if (LIST_BLOCK_TYPES.includes(type)) {
      level = Math.max(0, Math.min(Math.trunc(Number(block.level)) || 0, prevLevel + 1, MAX_LEVEL));
      prevLevel = level;
    } else {
      prevLevel = -1;
      if (type === BLOCK_HEADING) text = text.split('\n').join(' ');
      else if (!text) return;
    }
    result.push({ type, level, text });
  });
  return result;
}

// Slide content compared when deciding whether markdown and slides agree (ids and lines ignored).
function structureOf(slides) {
  return JSON.stringify(slides.map((s) => [s.kind, s.title, s.blocks.map((b) => [b.type, b.level, b.text])]));
}

// --- markdown -> slides ---

const HEADING_RE = /^ {0,3}(#{1,6})(?:[ \t]+(.*?))?[ \t]*$/s;
const LIST_RE = /^([ \t]*)([-*+]|\d{1,9}[.)])(?:[ \t]+(.*?))?[ \t]*$/s;
const BREAK_RE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;

// A line with its tabs expanded to columns of four.
function expandTabs(line) {
  let out = '';
  for (let i = 0; i < line.length; i += 1) {
    out += line[i] === '\t' ? ' '.repeat(4 - (out.length % 4)) : line[i];
  }
  return out;
}

// Parses markdown into slides: "#" starts a title slide, "##" a chapter slide, "###" a normal
// slide; deeper headings are sub headings inside the slide. Text before the first heading becomes an untitled normal slide.
// Each slide is {kind, title, blocks, line} where line is its first markdown line (0-based).
function parseMarkdown(md) {
  const slides = [];
  let current = null;
  let stack = [];          // marker columns of the open list items
  let prevBlank = true;    // previous line was empty (a paragraph can't continue)
  let prevHeading = false; // previous line was a heading (a paragraph can't continue)

  const slideFor = (lineno) => {
    if (current === null) {
      current = { kind: KIND_NORMAL, title: '', blocks: [], line: lineno };
      slides.push(current);
    }
    return current;
  };

  normalizeNewlines(md).split('\n').forEach((raw, lineno) => {
    const line = expandTabs(raw);
    const stripped = line.trim();
    if (!stripped) {
      prevBlank = true;
      return;
    }
    let text;
    if (stripped.length > 1 && stripped[0] === '\\' && MD_ESCAPE_CHARS.includes(stripped[1])) {
      text = stripped.slice(1);
    } else {
      let m = line.match(HEADING_RE);
      if (m) {
        const kind = SLIDE_KIND_BY_HEADING_LEVEL[m[1].length];
        const title = cleanLine(m[2] || '');
        if (kind) {
          current = { kind, title, blocks: [], line: lineno };
          slides.push(current);
        } else {
          slideFor(lineno).blocks.push({ type: BLOCK_HEADING, level: 0, text: title });
        }
        stack = [];
        prevBlank = false;
        prevHeading = true;
        return;
      }
      if (BREAK_RE.test(line)) {
        stack = [];
        prevBlank = true;
        return;
      }
      m = line.match(LIST_RE);
      if (m) {
        const indent = m[1].length;
        while (stack.length && stack[stack.length - 1] > indent) stack.pop();
        if (stack.length && stack[stack.length - 1] === indent) stack.pop();
        const level = Math.min(stack.length, MAX_LEVEL);
        stack.push(indent);
        const type = '-*+'.includes(m[2]) ? BLOCK_BULLET : BLOCK_NUMBER;
        slideFor(lineno).blocks.push({ type, level, text: cleanLine(m[3] || '') });
        prevBlank = false;
        prevHeading = false;
        return;
      }
      text = stripped;
    }
    const { blocks } = slideFor(lineno);
    text = cleanLine(text);
    const last = blocks[blocks.length - 1];
    if (!prevBlank && !prevHeading && last && last.type !== BLOCK_HEADING) {
      last.text = last.text ? `${last.text}\n${text}` : text;
    } else {
      blocks.push({ type: BLOCK_PARA, level: 0, text });
      stack = [];
    }
    prevBlank = false;
    prevHeading = false;
  });

  slides.forEach((slide) => { slide.blocks = normalizeBlocks(slide.blocks); });
  return slides;
}

// First markdown line (0-based) of each slide.
function slideLines(md) {
  return parseMarkdown(md).map((s) => s.line);
}

// --- slides -> markdown ---

// Returns the text line, escaped when it would otherwise read as markdown structure.
function escapeLine(text) {
  if ((text.length > 1 && text[0] === '\\' && MD_ESCAPE_CHARS.includes(text[1]))
      || HEADING_RE.test(text) || LIST_RE.test(text) || BREAK_RE.test(text)) {
    return `\\${text}`;
  }
  return text;
}

// Markdown lines of one slide's body blocks.
function blocksToLines(blocks) {
  const lines = [];
  let counters = new Array(MAX_LEVEL + 1).fill(0); // number of the last numbered item per level
  const widths = new Array(MAX_LEVEL + 1).fill(2); // marker width ("- " / "12. ") of the last item per level
  let prevList = false;
  blocks.forEach(({ type, level, text }) => {
    const isList = LIST_BLOCK_TYPES.includes(type);
    if (!(isList && prevList)) lines.push('');
    const textLines = text ? text.split('\n') : [];
    if (isList) {
      counters.fill(0, level + 1);
      let marker;
      if (type === BLOCK_NUMBER) {
        counters[level] += 1;
        marker = `${counters[level]}.`;
      } else {
        counters[level] = 0;
        marker = '-';
      }
      const indent = ' '.repeat(widths.slice(0, level).reduce((sum, w) => sum + w, 0));
      widths[level] = marker.length + 1;
      lines.push(textLines.length ? `${indent}${marker} ${textLines[0]}` : `${indent}${marker}`);
      const cont = ' '.repeat(indent.length + widths[level]);
      textLines.slice(1).forEach((t) => lines.push(cont + escapeLine(t)));
    } else {
      counters = new Array(MAX_LEVEL + 1).fill(0);
      if (type === BLOCK_HEADING) lines.push(text ? `${SUB_HEADING_MARK} ${text}` : SUB_HEADING_MARK);
      else textLines.forEach((t) => lines.push(escapeLine(t)));
    }
    prevList = isList;
  });
  return lines;
}

// Markdown for slides ({kind, title, blocks}); the inverse of parseMarkdown.
function slidesToMarkdown(slides) {
  const out = [];
  slides.forEach((slide) => {
    if (out.length) out.push('');
    const mark = SLIDE_HEADING_MARKS[slide.kind];
    out.push(slide.title ? `${mark} ${slide.title}` : mark);
    out.push(...blocksToLines(slide.blocks));
  });
  return out.length ? `${out.join('\n')}\n` : '';
}

// --- layouts ---

// Every slide kind and slot on the default pattern.
function defaultLayouts() {
  const layouts = {};
  KINDS.forEach((kind) => {
    layouts[kind] = {};
    LAYOUT_SLOTS.forEach((slot) => { layouts[kind][slot] = DEFAULT_LAYOUT_PATTERN; });
  });
  return layouts;
}

// Complete, valid choices from any input: unknown kinds, slots and patterns are ignored.
function normalizeLayouts(raw) {
  const layouts = defaultLayouts();
  if (!isRecord(raw)) return layouts;
  Object.entries(raw).forEach(([kind, slots]) => {
    if (!KINDS.includes(kind) || !isRecord(slots)) return;
    Object.entries(slots).forEach(([slot, pattern]) => {
      if (LAYOUT_SLOTS.includes(slot) && LAYOUT_PATTERNS.includes(pattern)) layouts[kind][slot] = pattern;
    });
  });
  return layouts;
}

const COLOR_RE = /^[0-9A-Fa-f]{6}$/;

// Whether a value is a usable color, or null for the theme's.
function validColor(value) {
  return value === null || (typeof value === 'string' && COLOR_RE.test(value));
}

// Whether a text property value can be used for a text type.
function validStyleValue(slot, prop, value) {
  if (prop === 'font') return value === null || FONT_CHOICES.includes(value);
  if (prop === 'size') return value === null || FONT_SIZE_CHOICES.includes(value);
  if (prop === 'color') return validColor(value);
  if (prop === 'bold' || prop === 'italic' || prop === 'underline') return typeof value === 'boolean';
  if (prop === 'char') return slot === BLOCK_BULLET && BULLET_CHOICES.includes(value);
  if (prop === 'scheme') return slot === BLOCK_NUMBER && typeof value === 'string' && Object.hasOwn(NUMBER_SCHEMES, value);
  return false;
}

// Only the valid text properties: known slide kind and text type, usable value.
function normalizeStyles(raw) {
  const styles = {};
  if (!isRecord(raw)) return styles;
  Object.entries(raw).forEach(([kind, slots]) => {
    if (!KINDS.includes(kind) || !isRecord(slots)) return;
    Object.entries(slots).forEach(([slot, props]) => {
      if (!TEXT_SLOTS.includes(slot) || !isRecord(props)) return;
      const valid = {};
      Object.entries(props).forEach(([prop, value]) => {
        if (validStyleValue(slot, prop, value)) valid[prop] = value;
      });
      if (valid.color) valid.color = valid.color.toUpperCase();
      if (Object.keys(valid).length) {
        styles[kind] = styles[kind] || {};
        styles[kind][slot] = valid;
      }
    });
  });
  return styles;
}

// A text type's look on a slide kind: defaults with what was specified in the app applied.
function textStyle(styles, kind, slot) {
  const specified = ((styles || {})[kind] || {})[slot] || {};
  return { ...TEXT_STYLE_DEFAULTS, ...TEXT_DEFAULTS[kind][slot], ...specified };
}

// Every slide kind with the default background and no footer.
function defaultDesigns() {
  const designs = {};
  KINDS.forEach((kind) => { designs[kind] = { ...DESIGN_DEFAULTS }; });
  return designs;
}

// Whether a background / footer property value can be used.
function validDesignValue(prop, value, images) {
  if (prop === 'bg_color') return validColor(value);
  if (prop === 'bg_image') return value === null || (typeof value === 'string' && Object.hasOwn(images, value));
  if (prop === 'footer_text') return typeof value === 'string';
  if (prop === 'show_number' || prop === 'show_date') return typeof value === 'boolean';
  return false;
}

// Complete background and footer settings from any input: unknown kinds and properties,
// unusable values and images the deck doesn't hold are ignored.
function normalizeDesigns(raw, images) {
  const designs = defaultDesigns();
  if (!isRecord(raw)) return designs;
  Object.entries(raw).forEach(([kind, props]) => {
    if (!KINDS.includes(kind) || !isRecord(props)) return;
    const design = designs[kind];
    Object.entries(props).forEach(([prop, value]) => {
      if (validDesignValue(prop, value, images || {})) design[prop] = value;
    });
    design.footer_text = cleanLine(design.footer_text.replace(/\n/g, ' '));
    if (design.bg_color) design.bg_color = design.bg_color.toUpperCase();
  });
  return designs;
}

// Name of a background image, from its content; throws unless it is a PNG or JPEG of usable size.
async function imageName(data) {
  if (data.length > MAX_IMAGE_BYTES) {
    throw new Error(`The image is too large (limit ${MAX_IMAGE_BYTES / (1024 * 1024)} MB).`);
  }
  const extension = Object.keys(IMAGE_SIGNATURES).find((ext) => IMAGE_SIGNATURES[ext].every((byte, i) => data[i] === byte));
  if (!extension) throw new Error('Background images must be PNG or JPEG files.');
  const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', data));
  const hex = Array.from(digest, (byte) => byte.toString(16).padStart(2, '0')).join('');
  return `bg_${hex.slice(0, 32)}.${extension}`;
}

// Content type of a background image name.
function imageContentType(name) {
  return IMAGE_CONTENT_TYPES[name.split('.').pop()];
}

// Only the images the settings use.
function usedImages(designs, images) {
  const used = {};
  Object.values(designs).forEach(({ bg_image: name }) => {
    if (name && Object.hasOwn(images, name)) used[name] = images[name];
  });
  return used;
}

// A background image as a blob the screen can make a URL for.
function imageBlob(name, data) {
  return new Blob([data], { type: imageContentType(name) });
}

// A layout state with each kind's background image URL filled in from urls (image name -> URL).
function withBackgroundUrls(layouts, urls) {
  const view = {};
  Object.entries(layouts.view).forEach(([kind, entry]) => {
    view[kind] = { ...entry, bg_url: (entry.design.bg_image && urls[entry.design.bg_image]) || null };
  });
  return { ...layouts, view };
}

// Nearest whole number; exact halves go to the even neighbour.
function roundHalfEven(value) {
  const floor = Math.floor(value);
  if (value - floor !== 0.5) return Math.round(value);
  return floor % 2 === 0 ? floor : floor + 1;
}

// Text size (1/100 pt) of a body block: the specified or base size, deeper levels in the base ratio.
function textSize(kind, level, style) {
  const base = BODY_SIZES[kind];
  if (!style.size) return base[level];
  return roundHalfEven((style.size * base[level]) / base[0] / 100) * 100;
}

// The look the screen draws for one slide kind under the chosen placement and text properties.
function layoutView(layouts, styles, designs) {
  const view = {};
  const usedDesigns = designs || defaultDesigns();
  const footerFrames = {};
  Object.entries(FOOTER_PLACEHOLDERS).forEach(([ph, spec]) => { footerFrames[ph] = { frame: spec.frame, align: spec.align }; });
  KINDS.forEach((kind) => {
    const spec = SLIDE_LAYOUTS[kind][layouts[kind][SLOT_SLIDE]];
    const types = {};
    TEXT_SLOTS.forEach((slot) => {
      const style = textStyle(styles, kind, slot);
      types[slot] = { ...style, sizes: Array.from({ length: MAX_LEVEL + 1 }, (_, level) => textSize(kind, level, style)) };
    });
    const design = usedDesigns[kind];
    view[kind] = {
      ...spec,
      title_size: types[SLOT_TITLE].size || spec.title_size,
      types,
      design,
      footer_frames: footerFrames,
    };
  });
  return view;
}

// Everything the layout dialog offers.
function layoutCatalog() {
  const placements = {};
  KINDS.forEach((kind) => {
    placements[kind] = LAYOUT_PATTERNS.map((p) => ({ id: p, label: SLIDE_LAYOUTS[kind][p].label }));
  });
  return {
    placements,
    fonts: FONT_CHOICES,
    sizes: FONT_SIZE_CHOICES,
    bullets: BULLET_CHOICES,
    numbers: Object.entries(NUMBER_SCHEMES).map(([id, label]) => ({ id, label })),
  };
}

// --- XML helpers ---

// Fills the {name} slots of a template.
function fill(template, values) {
  return template.replace(/\{(\w+)\}/g, (slot, name) => (Object.hasOwn(values, name) ? values[name] : slot));
}

// Text as XML element content.
function escapeXml(text) {
  return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

// Text as an XML attribute value.
function escapeAttr(text) {
  return escapeXml(text).replace(/"/g, '&quot;');
}

// Attributes as XML attribute text.
function attrsText(attrs) {
  return Object.entries(attrs).map(([k, v]) => `${k}="${escapeAttr(v)}"`).join(' ');
}

// Parses XML text into its root element; throws when it is not well formed.
function parseXml(text) {
  const doc = new DOMParser().parseFromString(text, 'application/xml');
  if (doc.getElementsByTagName('parsererror').length) throw new Error('Invalid XML.');
  return doc.documentElement;
}

// Parses XML bytes into their root element.
function parseXmlBytes(data) {
  return parseXml(new TextDecoder().decode(data));
}

// XML text as the bytes of a standalone part.
function xmlPart(xml) {
  return new TextEncoder().encode(XML_DECLARATION + xml);
}

// Serializes an element as a standalone UTF-8 XML part.
function xmlBytes(root) {
  return xmlPart(new XMLSerializer().serializeToString(root));
}

// Document new elements are made in; they move to the tree they are added to.
const xmlFactory = new DOMParser().parseFromString('<root/>', 'application/xml');

// New element "a:p" with attributes, added to a parent when given. An attribute name
// with a prefix ("r:id") goes in that namespace.
function xmlElement(name, attrs, parent) {
  const el = xmlFactory.createElementNS(NS[name.split(':')[0]], name);
  Object.entries(attrs || {}).forEach(([key, value]) => {
    if (key.includes(':')) el.setAttributeNS(NS[key.split(':')[0]], key, value);
    else el.setAttribute(key, value);
  });
  if (parent) parent.appendChild(el);
  return el;
}

// Whether an element is "a:p".
function isElement(el, name) {
  const [prefix, local] = name.split(':');
  return el.namespaceURI === NS[prefix] && el.localName === local;
}

// Direct children "a:p" of an element.
function childrenOf(el, name) {
  return Array.from(el.children).filter((child) => isElement(child, name));
}

// First element down a path of direct children ("p:cSld", "p:spTree"), or null.
function findChild(el, ...path) {
  let current = el;
  path.forEach((name) => { current = current && (childrenOf(current, name)[0] || null); });
  return current;
}

// All descendants "a:p" of an element, in document order.
function descendantsOf(el, name) {
  const [prefix, local] = name.split(':');
  return Array.from(el.getElementsByTagNameNS(NS[prefix], local));
}

// Serializes a relationships part from {id: [type, target]}.
function relsBytes(rels) {
  const items = Object.entries(rels)
    .map(([rid, [type, target]]) => `<Relationship ${attrsText({ Id: rid, Type: type, Target: target })}/>`)
    .join('');
  return xmlPart(`<Relationships xmlns="${NS.rel}">${items}</Relationships>`);
}

// Parses a relationships part into {id: [type, target]}.
function parseRels(data) {
  const rels = {};
  childrenOf(parseXmlBytes(data), 'rel:Relationship').forEach((el) => {
    if (el.getAttribute('TargetMode') !== 'External') rels[el.getAttribute('Id')] = [el.getAttribute('Type'), el.getAttribute('Target')];
  });
  return rels;
}

// Folder of a package path ("" at the top).
function dirName(path) {
  const cut = path.lastIndexOf('/');
  return cut < 0 ? '' : path.slice(0, cut);
}

// Path of the relationships part of a part ("ppt/slides/slide1.xml" -> "ppt/slides/_rels/slide1.xml.rels").
function relsPath(part) {
  const folder = dirName(part);
  return folder ? `${folder}/_rels/${part.slice(folder.length + 1)}.rels` : `_rels/${part}.rels`;
}

// Resolves a relationship target against the folder of its source part.
function resolvePart(sourcePart, target) {
  if (target.startsWith('/')) return target.replace(/^\/+/, '');
  const parts = [];
  `${dirName(sourcePart)}/${target}`.split('/').forEach((piece) => {
    if (piece === '..') parts.pop();
    else if (piece && piece !== '.') parts.push(piece);
  });
  return parts.join('/');
}

// Path of a part relative to a folder.
function relativePath(part, folder) {
  const from = folder ? folder.split('/') : [];
  const to = part.split('/');
  let same = 0;
  while (same < from.length && from[same] === to[same]) same += 1;
  return [...new Array(from.length - same).fill('..'), ...to.slice(same)].join('/');
}

// Next free "rIdN" in a relationships object.
function nextRid(rels) {
  const numbers = Object.keys(rels).map((rid) => rid.match(/^rId(\d+)$/)).filter(Boolean).map((m) => Number(m[1]));
  return `rId${Math.max(0, ...numbers) + 1}`;
}

// --- paragraphs ---

// Adds a run-properties element (a:rPr / a:endParaRPr) with a text style.
function addRunProps(parent, tag, style) {
  const look = style || {};
  const attrs = { lang: TEXT_LANG, altLang: TEXT_ALT_LANG };
  if (look.size) attrs.sz = String(look.size);
  if (look.bold) attrs.b = '1';
  if (look.italic) attrs.i = '1';
  if (look.underline) attrs.u = 'sng';
  const props = xmlElement(tag, attrs, parent);
  if (look.color) xmlElement('a:srgbClr', { val: look.color }, xmlElement('a:solidFill', {}, props));
  if (look.font) {
    xmlElement('a:latin', { typeface: look.font }, props);
    xmlElement('a:ea', { typeface: look.font }, props);
  }
}

// Appends runs (and a:br for line breaks) for text to an a:p.
function appendRuns(p, text, style) {
  (text ? text.split('\n') : []).forEach((line, i) => {
    if (i) addRunProps(xmlElement('a:br', {}, p), 'a:rPr', style);
    const run = xmlElement('a:r', {}, p);
    addRunProps(run, 'a:rPr', style);
    xmlElement('a:t', {}, run).textContent = line;
  });
  addRunProps(p, 'a:endParaRPr', style);
}

// Builds the a:p of one body block. The block type is carried by real paragraph formatting:
// buChar = bullet, buAutoNum = numbered, buNone with level 0 = sub heading, buNone with level 1 = plain text.
// Everything else about the look comes from the slide kind's placement and text properties.
function blockParagraph(block, kind, layouts, styles) {
  const p = xmlElement('a:p');
  const { type, level } = block;
  const style = textStyle(styles, kind, type);
  const align = SLIDE_LAYOUTS[kind][layouts[kind][SLOT_SLIDE]].body_align;
  if (LIST_BLOCK_TYPES.includes(type)) {
    const ppr = xmlElement('a:pPr', {
      marL: String(LIST_MARGIN + level * LEVEL_INDENT), lvl: String(level), indent: String(-LIST_HANG), algn: align,
    }, p);
    if (type === BLOCK_NUMBER) {
      xmlElement('a:buFont', { typeface: NUMBER_FONT }, ppr);
      xmlElement('a:buAutoNum', { type: style.scheme }, ppr);
    } else {
      xmlElement('a:buFont', { typeface: BULLET_FONT }, ppr);
      xmlElement('a:buChar', { char: style.char }, ppr);
    }
  } else {
    const ppr = xmlElement('a:pPr', {
      marL: '0', indent: '0', algn: align, lvl: type === BLOCK_HEADING ? HEADING_PARA_LEVEL : PLAIN_PARA_LEVEL,
    }, p);
    xmlElement('a:buNone', {}, ppr);
  }
  appendRuns(p, block.text, { ...style, size: textSize(kind, level, style) });
  return p;
}

// Builds the a:p of a title (its look comes from the layout).
function titleParagraph(title) {
  const p = xmlElement('a:p');
  appendRuns(p, title, null);
  return p;
}

// Text of an a:p (a:br as newlines).
function paragraphText(p) {
  return Array.from(p.children).map((child) => {
    if (isElement(child, 'a:r') || isElement(child, 'a:fld')) {
      return descendantsOf(child, 'a:t').map((t) => t.textContent).join('');
    }
    return isElement(child, 'a:br') ? '\n' : '';
  }).join('');
}

// Reads one body a:p back into a block, or null for an empty plain paragraph.
function readParagraph(p) {
  const ppr = findChild(p, 'a:pPr');
  const lvl = ppr ? ppr.getAttribute('lvl') : null;
  const level = lvl === null ? 0 : Number(lvl);
  let type;
  if (ppr && findChild(ppr, 'a:buAutoNum')) {
    type = BLOCK_NUMBER;
  } else if (ppr && (findChild(ppr, 'a:buChar') || findChild(ppr, 'a:buBlip'))) {
    type = BLOCK_BULLET;
  } else {
    type = lvl === HEADING_PARA_LEVEL ? BLOCK_HEADING : BLOCK_PARA;
  }
  const text = paragraphText(p);
  if (type === BLOCK_PARA && !cleanText(text)) return null;
  return { type, level, text };
}

// --- slide shapes ---

// Placeholder element (p:ph) of a shape, or null.
function placeholderOf(sp) {
  return findChild(sp, 'p:nvSpPr', 'p:nvPr', 'p:ph');
}

// Returns the [title, body] placeholder shapes of a slide; either may be null.
function findShapes(sld) {
  let title = null;
  let body = null;
  descendantsOf(sld, 'p:sp').forEach((sp) => {
    const ph = placeholderOf(sp);
    if (!ph) return;
    const type = ph.getAttribute('type') || 'obj';
    const isTitle = TITLE_PH_TYPES.includes(type);
    if (isTitle && !title) title = sp;
    else if ((ph.getAttribute('idx') === '1' || BODY_PH_TYPES.includes(type)) && !isTitle && !body) body = sp;
  });
  return [title, body];
}

// New slide XML of a kind, with empty title and body.
function newSlideXml(kind) {
  return parseXml(fill(SLIDE_XML, { title_ph: attrsText(TITLE_PH_ATTRS[kind]), body_ph: attrsText(BODY_PH_ATTRS[kind]) }));
}

// Returns the [title, body] shapes of a slide, adding them from the slide template when missing.
function ensureShapes(sld, kind) {
  const [title, body] = findShapes(sld);
  if (title && body) return [title, body];
  const templates = findShapes(newSlideXml(kind));
  const tree = findChild(sld, 'p:cSld', 'p:spTree');
  const used = descendantsOf(sld, 'p:cNvPr').map((el) => Number(el.getAttribute('id') || 0));
  [title, body].forEach((existing, i) => {
    if (existing) return;
    const newId = Math.max(...used) + 1;
    used.push(newId);
    findChild(templates[i], 'p:nvSpPr', 'p:cNvPr').setAttribute('id', String(newId));
    tree.appendChild(templates[i]);
  });
  return findShapes(sld);
}

// Replaces the paragraphs of a shape's text body.
function setParagraphs(sp, paragraphs) {
  const txBody = findChild(sp, 'p:txBody');
  childrenOf(txBody, 'a:p').forEach((p) => txBody.removeChild(p));
  let content = paragraphs;
  if (!content.length) {
    const empty = xmlElement('a:p');
    addRunProps(empty, 'a:endParaRPr', null);
    content = [empty];
  }
  content.forEach((p) => txBody.appendChild(p));
}

// --- deck ---

// One presentation held as OOXML parts in memory.
// Slides are kept as parsed XML (`slides`: sldId id -> record) in presentation order (`order`);
// every other part is kept as bytes and written back as it is.
class Deck {
  constructor(parts, overrides, presentation, presRels, order, slides, layouts, styles, designs, images) {
    this.parts = parts;
    this.overrides = overrides;
    this.presentation = presentation;
    this.presRels = presRels;
    this.order = order;
    this.slides = slides;     // Map: id -> {part, rid, xml, rels}
    this.layouts = layouts;   // slide kind -> slot -> chosen pattern
    this.styles = styles || {};  // slide kind -> text type -> specified properties
    this.designs = designs || defaultDesigns();  // slide kind -> background and footer properties
    this.images = images || {};  // background image name -> bytes (written to the package when used)
    this.layoutKinds = this.readLayoutKinds();
  }

  // Slide kind by layout part path, from each layout's p:sldLayout@type.
  readLayoutKinds() {
    const kinds = {};
    Object.entries(this.parts).forEach(([path, data]) => {
      if (SLIDE_LAYOUT_PART_RE.test(path)) {
        const type = parseXmlBytes(data).getAttribute('type') || '';
        kinds[path] = Object.hasOwn(KIND_BY_LAYOUT_TYPE, type) ? KIND_BY_LAYOUT_TYPE[type] : KIND_NORMAL;
      }
    });
    return kinds;
  }
}

// One text placeholder of a layout or the master.
function placeholderShape(id, name, ph, frame, anchor, listStyle, prompt) {
  const [x, y, cx, cy] = frame;
  return fill(PH_SHAPE, { id, name, ph, anchor, lst: listStyle, prompt, x, y, cx, cy });
}

// Date, footer text and slide number shapes from what each holds; phText gives each its p:ph attributes.
function footerShapes(contents, phText) {
  return Object.entries(FOOTER_PLACEHOLDERS).map(([ph, spec]) => {
    const [x, y, cx, cy] = spec.frame;
    return fill(FOOTER_SHAPE, {
      id: spec.id, name: spec.name, ph: phText(spec), align: spec.align, x, y, cx, cy, content: contents[ph],
    });
  }).join('');
}

// What the date or slide number shape of the master and the layouts holds.
function footerFieldXml(ph, text) {
  const [id, type] = FOOTER_FIELDS[ph];
  return fill(FOOTER_FIELD_XML, { id, type, text });
}

// Footer shapes of the master.
function masterFooterShapes() {
  return footerShapes({
    [FOOTER_DATE]: footerFieldXml(FOOTER_DATE, FOOTER_DATE_SAMPLE),
    [FOOTER_TEXT]: FOOTER_EMPTY_XML,
    [FOOTER_NUMBER]: footerFieldXml(FOOTER_NUMBER, FOOTER_NUMBER_SAMPLE),
  }, (spec) => spec.master_ph);
}

// XML of the slide master.
function slideMasterXml() {
  const textShapes = MASTER_TEXT_SHAPES.map((spec) => placeholderShape(
    spec.id, spec.name, spec.ph, spec.frame, spec.anchor, '<a:lstStyle/>', spec.prompt,
  )).join('');
  const levels = Array.from({ length: MAX_LEVEL + 1 }, (_, i) => fill(BODY_LEVEL_XML, {
    n: i + 1, margin: LIST_MARGIN + i * LEVEL_INDENT, hang: LIST_HANG, size: BODY_LEVEL_SIZES[i],
  })).join('');
  return fill(SLIDE_MASTER_XML, { shapes: textShapes + masterFooterShapes(), body_levels: levels });
}

// Footer shapes of a layout, carrying the footer text of its slide kind.
function layoutFooterShapes(design) {
  const text = design.footer_text;
  return footerShapes({
    [FOOTER_DATE]: footerFieldXml(FOOTER_DATE, FOOTER_DATE_SAMPLE),
    [FOOTER_TEXT]: text ? fill(FOOTER_RUN_XML, { text: escapeXml(text) }) : FOOTER_EMPTY_XML,
    [FOOTER_NUMBER]: footerFieldXml(FOOTER_NUMBER, FOOTER_NUMBER_SAMPLE),
  }, (spec) => attrsText(spec.ph));
}

// p:bg of a layout ("" keeps the master's background).
function layoutBackground(design) {
  if (design.bg_image) return fill(BACKGROUND_IMAGE_XML, { rid: LAYOUT_IMAGE_RID });
  if (design.bg_color) return fill(BACKGROUND_COLOR_XML, { color: design.bg_color });
  return '';
}

// XML of the layout part of a slide kind under a slide pattern.
function layoutXml(kind, pattern, title, design) {
  const spec = SLIDE_LAYOUTS[kind][pattern];
  const info = SLIDE_LAYOUT_INFO[kind];
  const attrs = `sz="${title.size || spec.title_size}"${title.bold ? ' b="1"' : ''}${title.italic ? ' i="1"' : ''}${title.underline ? ' u="sng"' : ''}`;
  let children = title.color ? `<a:solidFill><a:srgbClr val="${title.color}"/></a:solidFill>` : '';
  if (title.font) {
    const font = escapeAttr(title.font);
    children += `<a:latin typeface="${font}"/><a:ea typeface="${font}"/>`;
  }
  const titleStyle = `<a:lstStyle><a:lvl1pPr algn="${spec.title_align}"><a:defRPr ${attrs}>${children}</a:defRPr></a:lvl1pPr></a:lstStyle>`;
  const bodyStyle = kind === KIND_NORMAL ? '<a:lstStyle/>'
    : `<a:lstStyle><a:lvl1pPr marL="0" indent="0" algn="${spec.body_align}"><a:buNone/>`
      + `<a:defRPr sz="${BODY_SIZES[kind][0]}"/></a:lvl1pPr></a:lstStyle>`;
  return fill(SLIDE_LAYOUT_XML, {
    type: info.type,
    name: info.name,
    background: layoutBackground(design),
    footer_shapes: layoutFooterShapes(design),
    title_shape: placeholderShape(2, 'Title 1', attrsText(TITLE_PH_ATTRS[kind]), spec.title_frame, spec.title_anchor, titleStyle, info.title_prompt),
    body_shape: placeholderShape(3, 'Text Placeholder 2', attrsText(BODY_PH_ATTRS[kind]), spec.body_frame, 't', bodyStyle, info.body_prompt),
  });
}

// Layout part path of a slide kind.
function layoutPath(kind) {
  return resolvePart(`${SLIDES_DIR}/x.xml`, LAYOUT_TARGETS[kind]);
}

// All layout parts and their relationships under the chosen settings.
function layoutParts(layouts, styles, designs) {
  const usedDesigns = designs || defaultDesigns();
  const parts = {};
  KINDS.forEach((kind) => {
    const path = layoutPath(kind);
    const rels = { ...SLIDE_LAYOUT_RELS };
    if (usedDesigns[kind].bg_image) rels[LAYOUT_IMAGE_RID] = [REL_IMAGE, `${LAYOUT_MEDIA_DIR}/${usedDesigns[kind].bg_image}`];
    parts[path] = xmlPart(layoutXml(kind, layouts[kind][SLOT_SLIDE], textStyle(styles, kind, SLOT_TITLE), usedDesigns[kind]));
    parts[relsPath(path)] = relsBytes(rels);
  });
  return parts;
}

// A new, empty deck built from the templates in data.js.
function newDeck(layouts, styles, designs, images) {
  const chosen = normalizeLayouts(layouts);
  const chosenStyles = normalizeStyles(styles);
  const chosenDesigns = normalizeDesigns(designs, images);
  const parts = { [SLIDE_MASTER_PART]: xmlPart(slideMasterXml()), [ROOT_RELS_PART]: xmlPart(ROOT_RELS_XML) };
  Object.entries(STATIC_PARTS).forEach(([path, xml]) => { parts[path] = xmlPart(xml); });
  Object.entries(STATIC_RELS).forEach(([path, rels]) => { parts[path] = relsBytes(rels); });
  Object.assign(parts, layoutParts(chosen, chosenStyles, chosenDesigns));
  return new Deck(parts, { ...STATIC_OVERRIDES }, parseXml(PRESENTATION_XML), { ...PRESENTATION_RELS }, [], new Map(),
    chosen, chosenStyles, chosenDesigns, usedImages(chosenDesigns, images || {}));
}

// A deck holding the slides of a markdown text.
function deckFromMarkdown(md, layouts, styles, designs, images) {
  const deck = newDeck(layouts, styles, designs, images);
  applySlides(deck, parseMarkdown(md));
  return deck;
}

// Layout part path of a slide.
function layoutPartOf(rec) {
  const rel = Object.values(rec.rels).find(([type]) => type === REL_SLIDE_LAYOUT);
  return rel ? resolvePart(rec.part, rel[1]) : null;
}

// Kind of a slide, from the type of the layout it uses.
function slideKind(deck, sid) {
  return deck.layoutKinds[layoutPartOf(deck.slides.get(sid))] || KIND_NORMAL;
}

// Record of a slide id; throws when there is none.
function slideRecord(deck, sid) {
  if (!deck.slides.has(sid)) throw new Error(`Slide not found: ${sid}`);
  return deck.slides.get(sid);
}

// Reads one slide's XML into {id, kind, title, blocks}.
function readSlide(deck, sid) {
  const [titleSp, bodySp] = findShapes(slideRecord(deck, sid).xml);
  let title = '';
  if (titleSp) title = cleanLine(descendantsOf(titleSp, 'a:p').map(paragraphText).join(' ').replace(/\n/g, ' '));
  const blocks = bodySp ? descendantsOf(bodySp, 'a:p').map(readParagraph).filter(Boolean) : [];
  return { id: sid, kind: slideKind(deck, sid), title, blocks: normalizeBlocks(blocks) };
}

// All slides in presentation order, read from the slide XML.
function readSlides(deck) {
  return deck.order.map((sid) => readSlide(deck, sid));
}

// Markdown generated from the deck's slide XML.
function deckToMarkdown(deck) {
  return slidesToMarkdown(readSlides(deck));
}

// Writes a slide's body paragraphs under the deck's chosen patterns.
function writeBody(deck, sid, blocks) {
  const kind = slideKind(deck, sid);
  const [, bodySp] = ensureShapes(deck.slides.get(sid).xml, kind);
  setParagraphs(bodySp, blocks.map((b) => blockParagraph(b, kind, deck.layouts, deck.styles)));
}

// Writes title and blocks into a slide's XML; does nothing (returns false) when they're unchanged.
function writeSlide(deck, sid, title, blocks) {
  const newTitle = cleanLine(title.replace(/\n/g, ' '));
  const newBlocks = normalizeBlocks(blocks);
  const current = readSlide(deck, sid);
  const sameBlocks = JSON.stringify(current.blocks) === JSON.stringify(newBlocks);
  if (current.title === newTitle && sameBlocks) return false;
  const [titleSp] = ensureShapes(deck.slides.get(sid).xml, current.kind);
  if (current.title !== newTitle) setParagraphs(titleSp, newTitle ? [titleParagraph(newTitle)] : []);
  if (!sameBlocks) writeBody(deck, sid, newBlocks);
  return true;
}

// Rewrites every slide's body so it follows the deck's layout settings; the text stays as it is.
function restyleSlides(deck) {
  deck.order.forEach((sid) => writeBody(deck, sid, readSlide(deck, sid).blocks));
}

// Changes the placement and text properties (styles null = keep the current ones):
// layout parts and all slide bodies are rewritten.
function setLayouts(deck, layouts, styles) {
  deck.layouts = normalizeLayouts(layouts);
  if (styles !== null && styles !== undefined) deck.styles = normalizeStyles(styles);
  Object.assign(deck.parts, layoutParts(deck.layouts, deck.styles, deck.designs));
  restyleSlides(deck);
}

// Changes properties of one slide kind's background and footer; only the layout parts are rewritten
// (the shapes on the slides follow when the package is written).
function setDesign(deck, kind, changes) {
  if (!KINDS.includes(kind)) throw new Error(`Unknown slide kind: ${kind}`);
  deck.designs = normalizeDesigns({ ...deck.designs, [kind]: { ...deck.designs[kind], ...changes } }, deck.images);
  deck.images = usedImages(deck.designs, deck.images);
  Object.assign(deck.parts, layoutParts(deck.layouts, deck.styles, deck.designs));
}

// Makes an image the background of one slide kind.
async function setBackgroundImage(deck, kind, data) {
  const name = await imageName(data);
  deck.images[name] = data;
  setDesign(deck, kind, { bg_image: name });
}

// Switches a slide to another kind: layout relationship and placeholder types.
function setSlideKind(deck, sid, kind) {
  if (!KINDS.includes(kind)) throw new Error(`Unknown slide kind: ${kind}`);
  const rec = slideRecord(deck, sid);
  if (slideKind(deck, sid) === kind) return false;
  const { blocks } = readSlide(deck, sid);
  const target = LAYOUT_TARGETS[kind];
  if (deck.layoutKinds[resolvePart(rec.part, target)] !== kind) {
    throw new UserError(`This presentation has no layout for ${kind}.`);
  }
  Object.entries(rec.rels).forEach(([rid, [type]]) => {
    if (type === REL_SLIDE_LAYOUT) rec.rels[rid] = [REL_SLIDE_LAYOUT, target];
  });
  const [titleSp, bodySp] = ensureShapes(rec.xml, kind);
  [[titleSp, TITLE_PH_ATTRS[kind]], [bodySp, BODY_PH_ATTRS[kind]]].forEach(([sp, attrs]) => {
    const ph = placeholderOf(sp);
    Array.from(ph.attributes).forEach((attr) => ph.removeAttributeNode(attr));
    Object.entries(attrs).forEach(([key, value]) => ph.setAttribute(key, value));
  });
  writeBody(deck, sid, blocks);
  return true;
}

// Adds an empty slide part of a kind at an index of the slide order; returns its id.
function addSlide(deck, kind, index) {
  if (!KINDS.includes(kind)) throw new Error(`Unknown slide kind: ${kind}`);
  const sid = Math.max(MIN_SLIDE_ID - 1, ...deck.slides.keys()) + 1;
  const used = new Set(Array.from(deck.slides.values(), (rec) => rec.part));
  let number = 1;
  while (used.has(`${SLIDES_DIR}/${SLIDE_FILE_PREFIX}${number}.xml`)) number += 1;
  const part = `${SLIDES_DIR}/${SLIDE_FILE_PREFIX}${number}.xml`;
  const rid = nextRid(deck.presRels);
  deck.presRels[rid] = [REL_SLIDE, relativePath(part, dirName(PRESENTATION_PART))];
  deck.slides.set(sid, { part, rid, xml: newSlideXml(kind), rels: { rId1: [REL_SLIDE_LAYOUT, LAYOUT_TARGETS[kind]] } });
  deck.order.splice(index, 0, sid);
  return sid;
}

// Removes a slide part and its references.
function removeSlide(deck, sid) {
  const rec = slideRecord(deck, sid);
  delete deck.presRels[rec.rid];
  deck.slides.delete(sid);
  deck.order.splice(deck.order.indexOf(sid), 1);
}

// Longest run of equal items in a[alo, ahi) and b[blo, bhi): [start in a, start in b, length].
function longestMatch(a, alo, ahi, blo, bhi, positions) {
  let best = [alo, blo, 0];
  let lengths = new Map();
  for (let i = alo; i < ahi; i += 1) {
    const next = new Map();
    (positions.get(a[i]) || []).forEach((j) => {
      if (j >= blo && j < bhi) {
        const k = (lengths.get(j - 1) || 0) + 1;
        next.set(j, k);
        if (k > best[2]) best = [i - k + 1, j - k + 1, k];
      }
    });
    lengths = next;
  }
  return best;
}

// Runs of equal items of two lists, in order: the longest first, then the same on each side of it.
function matchingRuns(a, alo, ahi, blo, bhi, positions) {
  const [i, j, size] = longestMatch(a, alo, ahi, blo, bhi, positions);
  if (!size) return [];
  return [
    ...matchingRuns(a, alo, i, blo, j, positions),
    [i, j, size],
    ...matchingRuns(a, i + size, ahi, j + size, bhi, positions),
  ];
}

// Index pairs [i, j] of a and b that line up: the items of equal runs and, between two runs,
// the items replacing each other, position by position.
function alignedPairs(a, b) {
  const positions = new Map();
  b.forEach((item, j) => {
    if (!positions.has(item)) positions.set(item, []);
    positions.get(item).push(j);
  });
  const pairs = [];
  let i = 0;
  let j = 0;
  const pairUp = (count) => {
    for (let k = 0; k < count; k += 1) pairs.push([i + k, j + k]);
  };
  [...matchingRuns(a, 0, a.length, 0, b.length, positions), [a.length, b.length, 0]].forEach(([ai, bj, size]) => {
    pairUp(Math.min(ai - i, bj - j));
    i = ai;
    j = bj;
    pairUp(size);
    i += size;
    j += size;
  });
  return pairs;
}

// Brings the deck's slide XML in line with parsed slides, reusing existing slide parts:
// slides are matched by (kind, title) with a diff, edited titles pair up by position and
// moved sections by signature, so typing never deletes and recreates a slide.
// Only slides whose content differs are rewritten. Returns whether anything changed.
function applySlides(deck, specs) {
  const current = readSlides(deck);
  const signature = (s) => JSON.stringify([s.kind, s.title]);
  const oldSigs = current.map(signature);
  const newSigs = specs.map(signature);
  const pair = new Array(specs.length).fill(null);
  const used = new Set();
  alignedPairs(oldSigs, newSigs).forEach(([i, j]) => {
    pair[j] = i;
    used.add(i);
  });
  const leftovers = new Map();
  oldSigs.forEach((sig, i) => {
    if (used.has(i)) return;
    if (!leftovers.has(sig)) leftovers.set(sig, []);
    leftovers.get(sig).push(i);
  });
  newSigs.forEach((sig, j) => {
    if (pair[j] === null && (leftovers.get(sig) || []).length) {
      pair[j] = leftovers.get(sig).shift();
      used.add(pair[j]);
    }
  });

  let changed = false;
  const newOrder = [];
  specs.forEach((spec, j) => {
    let sid;
    if (pair[j] === null) {
      sid = addSlide(deck, spec.kind, deck.order.length);
      changed = true;
    } else {
      sid = current[pair[j]].id;
      if (setSlideKind(deck, sid, spec.kind)) changed = true;
    }
    if (writeSlide(deck, sid, spec.title, spec.blocks)) changed = true;
    newOrder.push(sid);
  });
  current.forEach((slide, i) => {
    if (!used.has(i)) {
      removeSlide(deck, slide.id);
      changed = true;
    }
  });
  if (JSON.stringify(deck.order) !== JSON.stringify(newOrder)) {
    deck.order = newOrder;
    changed = true;
  }
  return changed;
}

// End index (exclusive) of what moves with the slide at start: a chapter slide takes the
// normal slides under it, anything else moves alone.
function spanEnd(kinds, start) {
  let end = start + 1;
  if (kinds[start] === KIND_CHAPTER) {
    while (end < kinds.length && kinds[end] === KIND_NORMAL) end += 1;
  }
  return end;
}

// Index a chapter or title slide at start lands on when moved up: a neighbouring chapter is
// passed whole; normal slides without a chapter are passed whole by a chapter, one by one by a title.
function moveUpTarget(kinds, start) {
  if (kinds[start - 1] !== KIND_NORMAL) return start - 1;
  let k = start - 1;
  while (k >= 0 && kinds[k] === KIND_NORMAL) k -= 1;
  if (k >= 0 && kinds[k] === KIND_CHAPTER) return k;
  return kinds[start] === KIND_TITLE ? start - 1 : k + 1;
}

// Moves a slide one place up (-1) or down (+1). A chapter slide moves together with its normal
// slides, and chapter and title slides pass a neighbouring chapter whole. Returns whether the order changed.
function moveSlide(deck, sid, direction) {
  slideRecord(deck, sid);
  const { order } = deck;
  const kinds = order.map((s) => slideKind(deck, s));
  const i = order.indexOf(sid);
  if (direction !== -1 && direction !== 1) throw new Error('direction must be -1 or 1.');
  if (kinds[i] === KIND_NORMAL) {
    const j = i + direction;
    if (j < 0 || j >= order.length) return false;
    [order[i], order[j]] = [order[j], order[i]];
    return true;
  }
  const start = i;
  const end = spanEnd(kinds, i);
  if (direction < 0) {
    if (start === 0) return false;
    const target = moveUpTarget(kinds, start);
    deck.order = [...order.slice(0, target), ...order.slice(start, end), ...order.slice(target, start), ...order.slice(end)];
  } else {
    if (end >= order.length) return false;
    const nextEnd = spanEnd(kinds, end);
    deck.order = [...order.slice(0, start), ...order.slice(end, nextEnd), ...order.slice(start, end), ...order.slice(nextEnd)];
  }
  return true;
}

// --- slide footers ---

// Builds the a:p of a date, footer text or slide number shape.
function footerParagraph(ph, text, style) {
  const p = xmlElement('a:p');
  xmlElement('a:pPr', { algn: FOOTER_PLACEHOLDERS[ph].align }, p);
  if (Object.hasOwn(FOOTER_FIELDS, ph)) {
    const [id, type] = FOOTER_FIELDS[ph];
    const field = xmlElement('a:fld', { id, type }, p);
    addRunProps(field, 'a:rPr', style);
    xmlElement('a:t', {}, field).textContent = text;
    addRunProps(p, 'a:endParaRPr', style);
  } else {
    appendRuns(p, text, style);
  }
  return p;
}

// Date as the footer shows it.
function footerDate(today) {
  return `${today.getMonth() + 1}/${today.getDate()}/${today.getFullYear()}`;
}

// Puts the footer shapes of a slide in line with the settings of its kind.
// The body and title placeholders are never touched, so the markdown isn't affected.
function writeFooters(deck, sid, number, today) {
  const sld = deck.slides.get(sid).xml;
  const kind = slideKind(deck, sid);
  const design = deck.designs[kind];
  const tree = findChild(sld, 'p:cSld', 'p:spTree');
  childrenOf(tree, 'p:sp').forEach((sp) => {
    const ph = placeholderOf(sp);
    if (ph && Object.hasOwn(FOOTER_PLACEHOLDERS, ph.getAttribute('type') || '')) tree.removeChild(sp);
  });
  const texts = {
    [FOOTER_DATE]: design.show_date ? footerDate(today) : '',
    [FOOTER_TEXT]: design.footer_text,
    [FOOTER_NUMBER]: design.show_number ? String(number) : '',
  };
  const style = textStyle(deck.styles, kind, SLOT_FOOTER);
  Object.entries(texts).forEach(([ph, text]) => {
    if (!text) return;
    const spec = FOOTER_PLACEHOLDERS[ph];
    const newId = Math.max(...descendantsOf(sld, 'p:cNvPr').map((el) => Number(el.getAttribute('id') || 0))) + 1;
    const sp = parseXml(fill(SLIDE_FOOTER_SHAPE, { id: newId, name: spec.name, ph: attrsText(spec.ph) }));
    setParagraphs(sp, [footerParagraph(ph, text, style)]);
    tree.appendChild(sp);
  });
}

// --- package I/O ---

// Builds the [Content_Types].xml of the deck.
function contentTypesBytes(deck) {
  const overrides = { ...deck.overrides };
  deck.slides.forEach((rec) => { overrides[`/${rec.part}`] = CT_SLIDE; });
  const items = `<Default Extension="rels" ContentType="${CT_RELS}"/><Default Extension="xml" ContentType="${CT_XML}"/>`
    + Object.entries(IMAGE_CONTENT_TYPES).map(([ext, ct]) => `<Default Extension="${ext}" ContentType="${ct}"/>`).join('')
    + Object.entries(overrides).map(([name, ct]) => `<Override ${attrsText({ PartName: name, ContentType: ct })}/>`).join('');
  return xmlPart(`<Types xmlns="${NS.ct}">${items}</Types>`);
}

// presentation.xml with p:sldIdLst rebuilt from the deck's slide order.
function presentationBytes(deck) {
  const pres = deck.presentation.cloneNode(true);
  childrenOf(pres, 'p:sldIdLst').forEach((old) => pres.removeChild(old));
  if (deck.order.length) {
    const lst = xmlElement('p:sldIdLst');
    deck.order.forEach((sid) => xmlElement('p:sldId', { id: String(sid), 'r:id': deck.slides.get(sid).rid }, lst));
    let index = 0;
    Array.from(pres.children).forEach((el, k) => {
      if (PRESENTATION_BEFORE_SLIDES.includes(el.localName)) index = k + 1;
    });
    pres.insertBefore(lst, pres.children[index] || null);
  }
  return xmlBytes(pres);
}

// docProps/custom.xml holding the layout settings.
function customPropsBytes(layouts, styles, designs) {
  return xmlPart(fill(CUSTOM_PROPS_XML, { json: escapeXml(JSON.stringify({ choices: layouts, styles, designs })) }));
}

// Layout settings stored in a package: [placement, text properties, raw backgrounds and footers]
// (defaults for packages without them).
function readLayoutSettings(data) {
  const defaults = [defaultLayouts(), {}, {}];
  if (!data) return defaults;
  try {
    const prop = childrenOf(parseXmlBytes(data), 'custom:property').find((el) => el.getAttribute('name') === LAYOUTS_PROPERTY);
    if (!prop) return defaults;
    const settings = JSON.parse((findChild(prop, 'vt:lpwstr') || {}).textContent || '');
    if (!isRecord(settings)) return defaults;
    return [normalizeLayouts(settings.choices), normalizeStyles(settings.styles), settings.designs || {}];
  } catch (e) {
    return defaults;
  }
}

// Writes the deck as a .pptx (ZIP) package.
async function buildPptx(deck) {
  const slides = readSlides(deck);
  const title = (slides.find((s) => s.title) || {}).title || APP_NAME;
  const today = new Date();
  const now = `${today.toISOString().slice(0, 19)}Z`;
  deck.order.forEach((sid, i) => writeFooters(deck, sid, i + 1, today));
  const files = {
    [CONTENT_TYPES_PART]: contentTypesBytes(deck),
    [PRESENTATION_PART]: presentationBytes(deck),
    [relsPath(PRESENTATION_PART)]: relsBytes(deck.presRels),
    [CORE_PROPS_PART]: xmlPart(fill(CORE_PROPS_XML, { title: escapeXml(title), now })),
    [CUSTOM_PROPS_PART]: customPropsBytes(deck.layouts, deck.styles, deck.designs),
  };
  Object.entries(usedImages(deck.designs, deck.images)).forEach(([name, data]) => { files[`${MEDIA_DIR}/${name}`] = data; });
  deck.slides.forEach((rec) => {
    files[rec.part] = xmlBytes(rec.xml);
    files[relsPath(rec.part)] = relsBytes(rec.rels);
  });
  Object.entries(deck.parts).forEach(([path, data]) => {
    if (!Object.hasOwn(files, path)) files[path] = data;
  });
  const first = [CONTENT_TYPES_PART, ROOT_RELS_PART];
  const rest = Object.keys(files).filter((path) => !first.includes(path)).sort();
  const zip = new JSZip();
  [...first, ...rest].forEach((path) => zip.file(path, files[path], { createFolders: false }));
  return zip.generateAsync({ type: 'uint8array', compression: 'DEFLATE' });
}

// Takes the background images out of the package parts.
function takeImages(files) {
  const images = {};
  Object.keys(files).forEach((path) => {
    const name = path.slice(MEDIA_DIR.length + 1);
    if (dirName(path) === MEDIA_DIR && IMAGE_NAME_RE.test(name)) {
      images[name] = files[path];
      delete files[path];
    }
  });
  return images;
}

// All files of a ZIP package as bytes; throws when it is not a ZIP.
async function readZip(data) {
  let zip;
  try {
    zip = await JSZip.loadAsync(data);
  } catch (e) {
    throw new Error('Cannot read this as a PPTX (ZIP) file.');
  }
  const files = {};
  await Promise.all(Object.values(zip.files).filter((entry) => !entry.dir).map(async (entry) => {
    files[entry.name] = await entry.async('uint8array');
  }));
  return files;
}

// Reads a .pptx written by this app back into a deck (slides parsed from their XML).
async function loadPptx(data) {
  const files = await readZip(data);
  let application;
  let rootRels;
  let types;
  try {
    application = (findChild(parseXmlBytes(files[APP_PROPS_PART]), 'app:Application') || {}).textContent;
    rootRels = parseRels(files[ROOT_RELS_PART]);
    types = parseXmlBytes(files[CONTENT_TYPES_PART]);
  } catch (e) {
    throw new Error('This is not a PowerPoint package.');
  }
  if (application !== APP_NAME) throw new UserError(`Only PPTX files created with ${APP_NAME} can be opened.`);
  const officeRel = Object.values(rootRels).find(([type]) => type === REL_OFFICE_DOCUMENT);
  if (officeRel && officeRel[1].replace(/^\/+/, '') !== PRESENTATION_PART) {
    throw new Error('presentation.xml is not in the expected location.');
  }

  const presentation = parseXmlBytes(files[PRESENTATION_PART]);
  const presRels = parseRels(files[relsPath(PRESENTATION_PART)]);
  const customProps = files[CUSTOM_PROPS_PART];
  [PRESENTATION_PART, relsPath(PRESENTATION_PART), CONTENT_TYPES_PART, CORE_PROPS_PART, CUSTOM_PROPS_PART].forEach((path) => { delete files[path]; });
  const [layouts, styles, rawDesigns] = readLayoutSettings(customProps);
  const images = takeImages(files);
  const designs = normalizeDesigns(rawDesigns, images);

  const order = [];
  const slides = new Map();
  descendantsOf(presentation, 'p:sldId').forEach((el) => {
    const sid = Number(el.getAttribute('id'));
    const rid = el.getAttributeNS(NS.r, 'id');
    const [type, target] = presRels[rid] || [];
    if (type !== REL_SLIDE) throw new Error(`The reference to slide ${sid} is broken.`);
    const part = resolvePart(PRESENTATION_PART, target);
    const relsPart = relsPath(part);
    slides.set(sid, {
      part, rid, xml: parseXmlBytes(files[part]), rels: Object.hasOwn(files, relsPart) ? parseRels(files[relsPart]) : {},
    });
    delete files[part];
    delete files[relsPart];
    order.push(sid);
  });

  const overrides = {};
  childrenOf(types, 'ct:Override').forEach((el) => {
    if (el.getAttribute('ContentType') !== CT_SLIDE) overrides[el.getAttribute('PartName')] = el.getAttribute('ContentType');
  });
  overrides[`/${CUSTOM_PROPS_PART}`] = CT_CUSTOM_PROPS;
  Object.assign(files, layoutParts(layouts, styles, designs));
  const deck = new Deck(files, overrides, presentation, presRels, order, slides, layouts, styles, designs, usedImages(designs, images));
  restyleSlides(deck);
  return deck;
}

// Markdown and slides must say the same thing before anything is saved.
function ensureInSync(deck, md) {
  if (structureOf(parseMarkdown(md)) !== structureOf(readSlides(deck))) {
    throw new UserError('Markdown and slides do not match. Wait for sync to finish, then save.');
  }
}

// The file to save ('pptx' or 'md') as a Blob; refused when md and the slides disagree.
async function exportFile(session, format, md) {
  ensureInSync(session.deck, md);
  if (format === 'md') return new Blob([md], { type: CT_MARKDOWN });
  return new Blob([await buildPptx(session.deck)], { type: CT_PPTX });
}

// --- undo history ---

// Markdown snapshots for undo / redo. Consecutive edits with the same key that come in
// quick succession (typing) are merged into one step.
class UndoHistory {
  constructor(md) {
    this.entries = [md];
    this.index = 0;
    this.key = null;
    this.lastTime = 0;
    this.groupStart = 0;
  }

  // Records md as the newest state.
  push(md, key, now) {
    if (md === this.entries[this.index]) return;
    const merge = key !== null && key === this.key && this.index > 0 && this.index === this.entries.length - 1
      && now - this.lastTime < HISTORY_MERGE_SEC && now - this.groupStart < HISTORY_GROUP_MAX_SEC;
    if (merge) {
      this.entries[this.index] = md;
    } else {
      this.entries.length = this.index + 1;
      this.entries.push(md);
      if (this.entries.length > HISTORY_LIMIT) this.entries.shift();
      this.index = this.entries.length - 1;
      this.groupStart = now;
    }
    this.key = key;
    this.lastTime = now;
  }

  get canUndo() {
    return this.index > 0;
  }

  get canRedo() {
    return this.index < this.entries.length - 1;
  }

  // Steps back and returns that markdown.
  undo() {
    if (!this.canUndo) throw new UserError('Nothing to undo.');
    this.index -= 1;
    this.key = null;
    return this.entries[this.index];
  }

  // Steps forward and returns that markdown.
  redo() {
    if (!this.canRedo) throw new UserError('Nothing to redo.');
    this.index += 1;
    this.key = null;
    return this.entries[this.index];
  }
}

// --- editing session ---

// Seconds on a clock that only goes forward.
function monotonicSeconds() {
  return performance.now() / 1000;
}

// The presentation being edited: the deck XML, the markdown shown in the editor and the history.
class Session {
  constructor(md = SAMPLE_MARKDOWN, layouts, styles, designs, images) {
    this.reset(deckFromMarkdown(md, layouts, styles, designs, images), md);
  }

  // Starts over with a deck and its markdown (opened file); clears the history.
  reset(deck, md) {
    this.deck = deck;
    this.md = md;
    this.history = new UndoHistory(md);
  }

  // Starts over from a markdown text (new / opened .md file), keeping the layout settings.
  loadMarkdown(md) {
    const { layouts, styles, designs, images } = this.deck;
    this.reset(deckFromMarkdown(md, layouts, styles, designs, images), md);
  }

  // New layout patterns: the look changes, the text, the markdown and the undo history don't.
  applyLayouts(layouts, styles) {
    setLayouts(this.deck, layouts, styles);
  }

  // New background or footer of a slide kind; like layouts, not part of the undo history.
  applyDesign(kind, changes) {
    setDesign(this.deck, kind, changes);
  }

  // New background image of a slide kind.
  async applyBackgroundImage(kind, data) {
    await setBackgroundImage(this.deck, kind, data);
  }

  // Markdown typed in the editor: written into the slide XML.
  applyMarkdown(md, key = 'md', now = monotonicSeconds()) {
    applySlides(this.deck, parseMarkdown(md));
    this.md = md;
    this.history.push(md, key, now);
  }

  // One slide-editor operation: changes the slide XML, then regenerates the markdown from it.
  applyOp(op, now = monotonicSeconds()) {
    const { deck } = this;
    const name = op.op;
    const sid = op.id ?? null;
    if (sid !== null || name !== 'insert') slideRecord(deck, sid);
    let key = null;
    if (name === 'set_slide') {
      writeSlide(deck, sid, op.title || '', op.blocks || []);
      key = `slide:${sid}`;
    } else if (name === 'insert') {
      const kind = op.kind || KIND_NORMAL;
      const index = sid === null ? 0 : deck.order.indexOf(sid) + 1;
      const newId = addSlide(deck, kind, index);
      const blocks = kind === KIND_NORMAL ? [{ type: BLOCK_BULLET, level: 0, text: '' }] : [];
      writeSlide(deck, newId, DEFAULT_TITLES[kind] || '', blocks);
    } else if (name === 'delete') {
      removeSlide(deck, sid);
    } else if (name === 'move') {
      moveSlide(deck, sid, op.direction || 0);
    } else if (name === 'set_kind') {
      setSlideKind(deck, sid, op.kind);
    } else {
      throw new Error(`Unknown operation: ${name}`);
    }
    this.md = deckToMarkdown(deck);
    this.history.push(this.md, key, now);
  }

  undo() {
    this.restore(this.history.undo());
  }

  redo() {
    this.restore(this.history.redo());
  }

  restore(md) {
    applySlides(this.deck, parseMarkdown(md));
    this.md = md;
  }

  // Everything the screen needs after a change.
  state() {
    const { layouts, styles, designs, images } = this.deck;
    return {
      md: this.md,
      slides: readSlides(this.deck),
      lines: slideLines(this.md),
      can_undo: this.history.canUndo,
      can_redo: this.history.canRedo,
      layouts: {
        choices: layouts,
        styles,
        view: layoutView(layouts, styles, designs),
        catalog: layoutCatalog(),
      },
      images,
    };
  }
}

// --- browser storage ---
// The work stays in this browser between visits: the markdown and the layout settings with their
// images, kept apart because the settings change rarely and images are large.

// The IndexedDB database of that name, opened (and created when missing).
function openStorage(name) {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name, STORAGE_VERSION);
    request.onupgradeneeded = () => request.result.createObjectStore(STORAGE_STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

// Runs one request on the store of an open database (null when storage could not be opened);
// resolves with its result when the transaction is done.
function storageRequest(db, mode, makeRequest) {
  if (!db) return Promise.reject(new Error('Browser storage is not available'));
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(STORAGE_STORE, mode);
    const request = makeRequest(transaction.objectStore(STORAGE_STORE));
    transaction.oncomplete = () => resolve(request.result);
    transaction.onerror = () => reject(transaction.error);
    transaction.onabort = () => reject(transaction.error);
  });
}

// Keeps the markdown being edited.
function saveDraft(db, md) {
  return storageRequest(db, 'readwrite', (store) => store.put(md, STORAGE_KEY_DRAFT));
}

// Keeps a deck's layout settings and the images they use.
function saveSettings(db, deck) {
  const { layouts: choices, styles, designs, images } = deck;
  return storageRequest(db, 'readwrite', (store) => store.put({ choices, styles, designs, images }, STORAGE_KEY_SETTINGS));
}

// The session to start with: what the database of that name kept, else the sample with default
// settings. db is the open database for later saves; when storage fails it is null and
// storageError says why (otherwise null).
async function openSession(name = STORAGE_DB) {
  try {
    const db = await openStorage(name);
    const draft = await storageRequest(db, 'readonly', (store) => store.get(STORAGE_KEY_DRAFT));
    const settings = await storageRequest(db, 'readonly', (store) => store.get(STORAGE_KEY_SETTINGS));
    const { choices, styles, designs, images } = isRecord(settings) ? settings : {};
    const session = new Session(typeof draft === 'string' ? draft : SAMPLE_MARKDOWN, choices, styles, designs, isRecord(images) ? images : {});
    return { session, db, storageError: null };
  } catch (e) {
    return { session: new Session(), db: null, storageError: e.message || String(e) };
  }
}

// --- layout settings ---

// CSS properties of a slide's background (one entry of the layout view); an image replaces the color.
function backgroundCss(view) {
  if (view.bg_url) return { backgroundImage: `url("${view.bg_url}")`, backgroundSize: '100% 100%' };
  return view.design.bg_color ? { bgcolor: `#${view.design.bg_color}` } : {};
}

// What a slide's footer shows: [{ id, text }] for the shapes in use.
function footerItems(design, number, today) {
  const items = [
    [FOOTER_DATE, design.show_date ? footerDate(today) : ''],
    [FOOTER_TEXT, design.footer_text],
    [FOOTER_NUMBER, design.show_number ? String(number) : ''],
  ];
  return items.filter(([, text]) => text).map(([id, text]) => ({ id, text }));
}

// Text properties with one property of one text type changed.
function withStyleProp(styles, kind, slot, prop, value) {
  const kindStyles = styles[kind] || {};
  return { ...styles, [kind]: { ...kindStyles, [slot]: { ...(kindStyles[slot] || {}), [prop]: value } } };
}

// Text properties with one text type back to its defaults.
function withoutSlotStyle(styles, kind, slot) {
  const kindStyles = { ...(styles[kind] || {}) };
  delete kindStyles[slot];
  return { ...styles, [kind]: kindStyles };
}

// Whether anything was specified for a text type.
function hasSlotStyle(styles, kind, slot) {
  return !!(styles[kind] || {})[slot];
}

// CSS properties of a text style (one entry of view.types).
function textStyleCss(style) {
  return {
    fontWeight: style.bold ? 700 : 400,
    fontStyle: style.italic ? 'italic' : 'normal',
    fontFamily: style.font ? `"${style.font}", ${FONT_FALLBACK}` : 'inherit',
    color: style.color ? `#${style.color}` : 'inherit',
  };
}

// --- generation API ---

// The API could not be reached (not started, or a different port).
class ApiUnreachableError extends Error {}

// Calls the generation API; body (when given) is sent as JSON. Resolves with the JSON answer.
// signal (an AbortSignal) cancels the call.
async function api(path, body, signal) {
  let res;
  try {
    res = await fetch(API_BASE + path, body === undefined ? { signal } : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') throw e;
    throw new ApiUnreachableError(`Cannot reach the generation API at ${API_BASE}. Start it in the app folder: ${API_START_COMMAND}`);
  }
  const data = await res.json().catch(() => null);
  if (!res.ok) throw new Error((data && typeof data.detail === 'string' && data.detail) || `${res.status} ${res.statusText}`);
  return data;
}

// Whether the API at API_BASE is this app's.
async function apiAvailable() {
  try {
    const who = await api('/who');
    return !!who && who.name === API_NAME;
  } catch (e) {
    return false;
  }
}

// Markdown text as the app writes it; '' when it holds no slides.
function canonicalMarkdown(text) {
  return slidesToMarkdown(parseMarkdown(normalizeNewlines(text)));
}

// Markdown written by the API for a request: a new deck (mode GENERATE_NEW), or current revised
// (GENERATE_REVISE). Returned in the app's own form.
async function generateMarkdown(mode, request, current, signal) {
  if (!request.trim()) throw new UserError('Enter a request.');
  if (mode === GENERATE_REVISE && !current.trim()) throw new UserError('There is no markdown to revise.');
  const body = { request, current: mode === GENERATE_REVISE ? current : null };
  const { markdown } = await api('/api/generate', body, signal);
  const md = canonicalMarkdown(typeof markdown === 'string' ? markdown : '');
  if (!md) throw new UserError('The answer contained no slides.');
  return md;
}

// --- screen units ---

// Point size -> CSS size relative to the slide width.
function ptToCqw(pt) {
  return `${(pt / SLIDE_W_PT) * 100}cqw`;
}

// EMU -> percentage of a total length.
function emuToPct(emu, total) {
  return `${(emu / total) * 100}%`;
}

// EMU -> CSS size relative to the slide width.
function emuToCqw(emu) {
  return `${(emu / SLIDE_W) * 100}cqw`;
}

// CSS position of a placeholder frame on the slide.
function frameBox([x, y, w, h]) {
  return {
    position: 'absolute', left: emuToPct(x, SLIDE_W), top: emuToPct(y, SLIDE_H),
    width: emuToPct(w, SLIDE_W), height: emuToPct(h, SLIDE_H),
  };
}

// --- shortcut keys ---

// Whether a key event is Ctrl/Cmd+Z (undo).
function undoKey(e) {
  return (e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z';
}

// Whether a key event is Ctrl+Y / Ctrl+Shift+Z (redo).
function redoKey(e) {
  return (e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === 'y' || (e.shiftKey && e.key.toLowerCase() === 'z'));
}

// Whether a key event is Alt+N (bullet <-> numbered); by key position, so any input mode counts.
function numberingKey(e) {
  return e.altKey && !e.ctrlKey && !e.metaKey && e.code === 'KeyN';
}

// --- file names ---

// Download file name from the first slide title ("presentation" when there is none).
function downloadName(slides, ext) {
  const title = (slides.find((s) => s.title) || {}).title || 'presentation';
  const safe = title.replace(/[\\/:*?"<>|]+/g, '_').replace(/\s+/g, ' ').trim().slice(0, 60);
  return `${safe || 'presentation'}.${ext}`;
}

// --- text positions ---

// 0-based line number of a character offset.
function lineOfOffset(text, offset) {
  let line = 0;
  for (let i = 0; i < offset && i < text.length; i += 1) {
    if (text[i] === '\n') line += 1;
  }
  return line;
}

// Character offset where a 0-based line starts.
function offsetOfLine(text, line) {
  let offset = 0;
  for (let i = 0; i < line; i += 1) {
    const next = text.indexOf('\n', offset);
    if (next < 0) return text.length;
    offset = next + 1;
  }
  return offset;
}

// Maps a cursor offset in oldText to newText: offsets in the unchanged prefix stay,
// offsets in the unchanged suffix keep their distance from the end, others go to the edit's end.
function mapOffset(oldText, newText, offset) {
  let prefix = 0;
  const max = Math.min(oldText.length, newText.length);
  while (prefix < max && oldText[prefix] === newText[prefix]) prefix += 1;
  let suffix = 0;
  while (
    suffix < max - prefix
    && oldText[oldText.length - 1 - suffix] === newText[newText.length - 1 - suffix]
  ) suffix += 1;
  if (offset <= prefix) return offset;
  if (offset >= oldText.length - suffix) return newText.length - (oldText.length - offset);
  return newText.length - suffix;
}

// Index of the slide containing a markdown line, given each slide's first line.
function slideIndexAtLine(lines, line) {
  let index = -1;
  lines.forEach((start, i) => { if (start <= line) index = i; });
  return Math.max(index, lines.length ? 0 : -1);
}

// --- markdown highlighting ---

const HEADING_LINE_RE = /^( {0,3})(#{1,6})([ \t].*)?$/;
const LIST_LINE_RE = /^([ \t]*)([-*+]|\d{1,9}[.)])([ \t].*)?$/;
const ESCAPED_LINE_RE = /^([ \t]*)(\\)([\\#\-*+_0-9].*)$/;

// Splits one markdown line into [tokenClass, text] pieces (classes are keys of MD_COLORS).
function highlightLine(line) {
  let m = line.match(ESCAPED_LINE_RE);
  if (m) return [['text', m[1]], ['escape', m[2]], ['text', m[3]]];
  m = line.match(HEADING_LINE_RE);
  if (m) {
    const cls = `h${Math.min(m[2].length, 4)}`;
    return [['text', m[1]], [cls, m[2] + (m[3] || '')]];
  }
  m = line.match(LIST_LINE_RE);
  if (m) return [['text', m[1]], ['marker', m[2]], ['text', m[3] || '']];
  return [['text', line]];
}

// --- slide block editing ---
// Blocks in the slide editor are { key, type, level, text }; `key` only identifies the
// input on screen. Functions here return new arrays and never change their arguments.

// Editor draft of a slide, with fresh keys from makeKey().
function draftFromSlide(slide, makeKey) {
  return {
    title: slide.title,
    blocks: slide.blocks.map((b) => ({ ...b, key: makeKey() })),
  };
}

// Key generator that reuses the keys of an existing draft by position, then takes new ones from makeKey().
function keysFrom(draft, makeKey) {
  let i = 0;
  return () => (draft && draft.blocks[i] ? draft.blocks[i++].key : (i++, makeKey()));
}

// Blocks without their screen keys.
function plainBlocks(blocks) {
  return blocks.map(({ type, level, text }) => ({ type, level, text }));
}

// Whether a draft says the same thing as a slide.
function draftMatchesSlide(draft, slide) {
  return draft.title === slide.title
    && JSON.stringify(plainBlocks(draft.blocks)) === JSON.stringify(plainBlocks(slide.blocks));
}

// Text of a list number under a numbering scheme.
function formatNumber(n, scheme) {
  if (scheme === SCHEME_PAREN) return `${n})`;
  if (scheme === SCHEME_CIRCLE && n <= MAX_CIRCLED) return String.fromCodePoint(CIRCLED_ONE + n - 1);
  return `${n}.`;
}

// Number shown before each numbered block (null for other blocks), counted like the markdown.
function numberLabels(blocks, scheme) {
  const counters = new Array(MAX_LEVEL + 1).fill(0);
  return blocks.map((b) => {
    if (!LIST_BLOCK_TYPES.includes(b.type)) {
      counters.fill(0);
      return null;
    }
    counters.fill(0, b.level + 1);
    if (b.type !== BLOCK_NUMBER) {
      counters[b.level] = 0;
      return null;
    }
    counters[b.level] += 1;
    return formatNumber(counters[b.level], scheme);
  });
}

// Splits block i at pos (Enter). An empty list item steps out one level instead
// (or becomes plain text at level 0). Returns { blocks, focus: { index, pos } }.
function splitBlock(blocks, i, pos, makeKey) {
  const block = blocks[i];
  if (!block.text && LIST_BLOCK_TYPES.includes(block.type)) {
    const changed = block.level > 0 ? { ...block, level: block.level - 1 } : { ...block, type: BLOCK_PARA };
    return { blocks: blocks.map((b, k) => (k === i ? changed : b)), focus: { index: i, pos: 0 } };
  }
  const nextType = block.type === BLOCK_HEADING ? BLOCK_PARA : block.type;
  const head = { ...block, text: block.text.slice(0, pos) };
  const tail = { key: makeKey(), type: nextType, level: nextType === BLOCK_PARA ? 0 : block.level, text: block.text.slice(pos) };
  return {
    blocks: [...blocks.slice(0, i), head, tail, ...blocks.slice(i + 1)],
    focus: { index: i + 1, pos: 0 },
  };
}

// Backspace at the start of block i: a nested item steps out, a list item or heading
// becomes plain text, plain text joins the block before. Returns { blocks, focus } or null.
function backspaceBlock(blocks, i) {
  const block = blocks[i];
  if (LIST_BLOCK_TYPES.includes(block.type) && block.level > 0) {
    return { blocks: changeLevel(blocks, i, -1), focus: { index: i, pos: 0 } };
  }
  if (block.type !== BLOCK_PARA) {
    return { blocks: changeType(blocks, i, BLOCK_PARA), focus: { index: i, pos: 0 } };
  }
  if (i === 0) return null;
  const prev = blocks[i - 1];
  const joined = { ...prev, text: prev.text + block.text };
  return {
    blocks: [...blocks.slice(0, i - 1), joined, ...blocks.slice(i + 1)],
    focus: { index: i - 1, pos: prev.text.length },
  };
}

// Changes the list level of block i by delta (lists only; at most one deeper than the item before).
function changeLevel(blocks, i, delta) {
  const block = blocks[i];
  if (!LIST_BLOCK_TYPES.includes(block.type)) return blocks;
  const prev = blocks[i - 1];
  const maxLevel = prev && LIST_BLOCK_TYPES.includes(prev.type) ? prev.level + 1 : 0;
  const level = Math.max(0, Math.min(block.level + delta, maxLevel, MAX_LEVEL));
  return blocks.map((b, k) => (k === i ? { ...b, level } : b));
}

// Tab (+1) / Shift+Tab (-1) on block i moves it along the outline:
// sub heading <-> plain text <-> bullet at level 0 <-> deeper list levels.
function tabBlock(blocks, i, delta) {
  const block = blocks[i];
  if (LIST_BLOCK_TYPES.includes(block.type)) {
    return delta < 0 && block.level === 0 ? changeType(blocks, i, BLOCK_PARA) : changeLevel(blocks, i, delta);
  }
  if (block.type === BLOCK_HEADING) return delta > 0 ? changeType(blocks, i, BLOCK_PARA) : blocks;
  return changeType(blocks, i, delta > 0 ? BLOCK_BULLET : BLOCK_HEADING);
}

// Switches list item i between bullet and numbered, keeping its level; other blocks stay as they are.
function toggleNumbering(blocks, i) {
  const { type } = blocks[i];
  if (!LIST_BLOCK_TYPES.includes(type)) return blocks;
  return changeType(blocks, i, type === BLOCK_NUMBER ? BLOCK_BULLET : BLOCK_NUMBER);
}

// Changes the type of block i; plain text and headings are always level 0.
function changeType(blocks, i, type) {
  return blocks.map((b, k) => {
    if (k !== i) return b;
    return { ...b, type, level: LIST_BLOCK_TYPES.includes(type) ? b.level : 0 };
  });
}

// Inserts a new empty block after index i (-1 = at the top). Returns { blocks, focus }.
function insertBlock(blocks, i, type, makeKey) {
  const prev = blocks[i];
  const level = prev && LIST_BLOCK_TYPES.includes(type) && LIST_BLOCK_TYPES.includes(prev.type) ? prev.level : 0;
  const block = { key: makeKey(), type, level, text: '' };
  return { blocks: [...blocks.slice(0, i + 1), block, ...blocks.slice(i + 1)], focus: { index: i + 1, pos: 0 } };
}

// Removes block i. Returns { blocks, focus } (focus null when nothing is left).
function removeBlock(blocks, i) {
  const rest = [...blocks.slice(0, i), ...blocks.slice(i + 1)];
  if (!rest.length) return { blocks: rest, focus: null };
  const index = Math.max(0, i - 1);
  return { blocks: rest, focus: { index, pos: rest[index].text.length } };
}
