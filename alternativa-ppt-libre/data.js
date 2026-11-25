// data.js
// Constants, lookup tables and OOXML part templates used by common.js and index.html.

// Written into docProps/app.xml (and the theme names); only packages carrying it are accepted on import.
const APP_NAME = 'Alternativa ppt Libre';

// Name the generation API returns from /who. Must equal APP_NAME in data.py.
const API_NAME = 'alternativa-ppt-libre';

// --- generation API ---
// Markdown generation runs on the optional local API (api_server.py); everything else works without it.

// Keep the port in sync with --port in the start command (README.md).
const API_BASE = 'http://127.0.0.1:9031';

// Command shown when the API cannot be reached.
const API_START_COMMAND = '$env:PYTHONDONTWRITEBYTECODE = "1"; uvicorn api_server:app --host 127.0.0.1 --port 9031';

// While the generation dialog is open and the API is not answering, it is checked again this often (ms).
const API_RETRY_DELAY = 3000;

// Generation modes: write a new deck, or revise the markdown being written.
const GENERATE_NEW = 'new';
const GENERATE_REVISE = 'revise';

// --- slide model ---

// Slide kinds.
const KIND_TITLE = 'title';       // "# Heading"
const KIND_CHAPTER = 'chapter';   // "## Heading"
const KIND_NORMAL = 'normal';     // "### Heading"
const KINDS = [KIND_TITLE, KIND_CHAPTER, KIND_NORMAL];
const KIND_LABELS = { title: 'Title', chapter: 'Chapter', normal: 'Normal' };

// Body block types.
const BLOCK_PARA = 'para';        // plain text
const BLOCK_HEADING = 'heading';  // "#### Subheading"
const BLOCK_BULLET = 'bullet';    // "- Item"
const BLOCK_NUMBER = 'number';    // "1. Item"
const BLOCK_TYPES = [BLOCK_PARA, BLOCK_HEADING, BLOCK_BULLET, BLOCK_NUMBER];
const LIST_BLOCK_TYPES = [BLOCK_BULLET, BLOCK_NUMBER];

// Block types offered in the slide toolbar, in order.
const BLOCK_TYPE_LABELS = {
  para: 'Body',
  bullet: 'Bullet',
  number: 'Number',
  heading: 'Subheading',
};

// Deepest list level (PowerPoint paragraph levels are 0-8).
const MAX_LEVEL = 8;

// Text given to slides added from the slide editor.
const DEFAULT_TITLES = { title: 'New Title', chapter: 'New Chapter', normal: 'New Slide' };

// --- markdown ---

// Characters a leading backslash escapes, so text such as "- x" or "# x" survives as plain text.
const MD_ESCAPE_CHARS = '\\#-*+_0123456789';

// Markdown heading marker by slide kind.
const SLIDE_HEADING_MARKS = { title: '#', chapter: '##', normal: '###' };

// Slide kind started by a heading level; deeper headings are sub headings inside the slide.
const SLIDE_KIND_BY_HEADING_LEVEL = { 1: KIND_TITLE, 2: KIND_CHAPTER, 3: KIND_NORMAL };

// Markdown heading marker of an in-slide sub heading.
const SUB_HEADING_MARK = '####';

// Markdown the app starts with when nothing was kept from an earlier visit.
const SAMPLE_MARKDOWN = `# AI Adoption Proposal

Toward higher productivity

## Chapter 1: AI Adoption Strategy

Raising productivity with AI

### Current Challenges

- Labor shortage
- Knowledge tied to individuals
  - Procedures only the owner knows
- Underused data

### AI Adoption Policy

#### Core Policy

- Automate routine work
- Promote data use

## Chapter 2: Execution Plan

### Rollout Schedule

1. Planning
2. Pilot
3. Full rollout
`;

// --- undo history ---

// Most snapshots kept.
const HISTORY_LIMIT = 200;

// Edits of the same kind closer together than this (s) become one undo step...
const HISTORY_MERGE_SEC = 1.5;

// ...as long as the step has not been growing for longer than this (s).
const HISTORY_GROUP_MAX_SEC = 5.0;

// --- browser storage ---

// IndexedDB database and store keeping the work between visits, and the keys in that store.
const STORAGE_DB = 'alternativa-ppt-libre';
const STORAGE_VERSION = 1;
const STORAGE_STORE = 'workspace';
const STORAGE_KEY_DRAFT = 'draft';        // the markdown being edited
const STORAGE_KEY_SETTINGS = 'settings';  // { choices, styles, designs, images }

// --- OOXML: geometry (EMU) ---

// 16:9 slide.
const SLIDE_W = 12192000;
const SLIDE_H = 6858000;
const NOTES_W = 6858000;
const NOTES_H = 9144000;

// Paragraph left margin of a level-0 list item, added indent per level, and bullet hang.
const LIST_MARGIN = 342900;
const LEVEL_INDENT = 457200;
const LIST_HANG = 342900;

// Body text size (1/100 pt) per list level.
const BODY_LEVEL_SIZES = [2400, 2000, 1800, 1600, 1600, 1600, 1600, 1600, 1600];

// Language tags of written text runs.
const TEXT_LANG = 'en-US';
const TEXT_ALT_LANG = 'ja-JP';

// Bullet glyph and numbering scheme.
const BULLET_FONT = 'Arial';
const BULLET_CHAR = '•';
const NUMBER_FONT = '+mj-lt';
const NUMBER_SCHEME = 'arabicPeriod';

// --- OOXML: namespaces and types ---

const NS = {
  a: 'http://schemas.openxmlformats.org/drawingml/2006/main',
  r: 'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
  p: 'http://schemas.openxmlformats.org/presentationml/2006/main',
  ct: 'http://schemas.openxmlformats.org/package/2006/content-types',
  rel: 'http://schemas.openxmlformats.org/package/2006/relationships',
  app: 'http://schemas.openxmlformats.org/officeDocument/2006/extended-properties',
  custom: 'http://schemas.openxmlformats.org/officeDocument/2006/custom-properties',
  vt: 'http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes',
};

const RT_BASE = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
const REL_OFFICE_DOCUMENT = `${RT_BASE}officeDocument`;
const REL_EXTENDED_PROPS = `${RT_BASE}extended-properties`;
const REL_CORE_PROPS = 'http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties';
const REL_CUSTOM_PROPS = `${RT_BASE}custom-properties`;
const REL_SLIDE = `${RT_BASE}slide`;
const REL_SLIDE_LAYOUT = `${RT_BASE}slideLayout`;
const REL_SLIDE_MASTER = `${RT_BASE}slideMaster`;
const REL_THEME = `${RT_BASE}theme`;
const REL_PRES_PROPS = `${RT_BASE}presProps`;
const REL_VIEW_PROPS = `${RT_BASE}viewProps`;
const REL_TABLE_STYLES = `${RT_BASE}tableStyles`;
const REL_IMAGE = `${RT_BASE}image`;

const CT_BASE = 'application/vnd.openxmlformats-officedocument.';
const CT_RELS = 'application/vnd.openxmlformats-package.relationships+xml';
const CT_XML = 'application/xml';
const CT_PRESENTATION = `${CT_BASE}presentationml.presentation.main+xml`;
const CT_SLIDE = `${CT_BASE}presentationml.slide+xml`;
const CT_SLIDE_LAYOUT = `${CT_BASE}presentationml.slideLayout+xml`;
const CT_SLIDE_MASTER = `${CT_BASE}presentationml.slideMaster+xml`;
const CT_THEME = `${CT_BASE}theme+xml`;
const CT_PRES_PROPS = `${CT_BASE}presentationml.presProps+xml`;
const CT_VIEW_PROPS = `${CT_BASE}presentationml.viewProps+xml`;
const CT_TABLE_STYLES = `${CT_BASE}presentationml.tableStyles+xml`;
const CT_CORE_PROPS = 'application/vnd.openxmlformats-package.core-properties+xml';
const CT_EXTENDED_PROPS = `${CT_BASE}extended-properties+xml`;
const CT_CUSTOM_PROPS = `${CT_BASE}custom-properties+xml`;
const CT_PPTX = `${CT_BASE}presentationml.presentation`;
const CT_MARKDOWN = 'text/markdown;charset=utf-8';

// Background image types: file extension -> content type, and the bytes each file starts with.
const IMAGE_CONTENT_TYPES = { png: 'image/png', jpg: 'image/jpeg' };
const IMAGE_SIGNATURES = { png: [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a], jpg: [0xff, 0xd8, 0xff] };
const MAX_IMAGE_BYTES = 15 * 1024 * 1024;

// Name of a background image: its content hash and file extension.
const IMAGE_NAME_RE = /^bg_[0-9a-f]{32}\.(?:png|jpg)$/;

// --- OOXML: package layout ---

const CONTENT_TYPES_PART = '[Content_Types].xml';
const ROOT_RELS_PART = '_rels/.rels';
const PRESENTATION_PART = 'ppt/presentation.xml';
const CORE_PROPS_PART = 'docProps/core.xml';
const APP_PROPS_PART = 'docProps/app.xml';
const CUSTOM_PROPS_PART = 'docProps/custom.xml';
const SLIDE_MASTER_PART = 'ppt/slideMasters/slideMaster1.xml';
const SLIDE_LAYOUT_PART_RE = /^ppt\/slideLayouts\/[^/]+\.xml$/;

// Folder and file name of slide parts ("ppt/slides/slide3.xml").
const SLIDES_DIR = 'ppt/slides';
const SLIDE_FILE_PREFIX = 'slide';

// Folder of background images in the package, relative to the package and to a layout part.
const MEDIA_DIR = 'ppt/media';
const LAYOUT_MEDIA_DIR = '../media';

// Lowest p:sldId id allowed by the schema.
const MIN_SLIDE_ID = 256;

// Layout (relative to a slide part) used by each slide kind.
const LAYOUT_TARGETS = {
  normal: '../slideLayouts/slideLayout1.xml',
  chapter: '../slideLayouts/slideLayout2.xml',
  title: '../slideLayouts/slideLayout3.xml',
};

// Slide kind by p:sldLayout@type; other layout types read as normal slides.
const KIND_BY_LAYOUT_TYPE = { secHead: KIND_CHAPTER, title: KIND_TITLE };

// Placeholder attributes of the title and body shapes per slide kind.
const TITLE_PH_ATTRS = {
  normal: { type: 'title' },
  chapter: { type: 'title' },
  title: { type: 'ctrTitle' },
};
const BODY_PH_ATTRS = {
  normal: { idx: '1' },
  chapter: { type: 'body', idx: '1' },
  title: { type: 'subTitle', idx: '1' },
};

// Placeholder types read as the slide title / body.
const TITLE_PH_TYPES = ['title', 'ctrTitle'];
const BODY_PH_TYPES = ['body', 'obj', 'subTitle'];

// Relationships of ppt/presentation.xml other than slides (id -> [type, target]).
const PRESENTATION_RELS = {
  rId1: [REL_SLIDE_MASTER, 'slideMasters/slideMaster1.xml'],
  rId2: [REL_PRES_PROPS, 'presProps.xml'],
  rId3: [REL_VIEW_PROPS, 'viewProps.xml'],
  rId4: [REL_THEME, 'theme/theme1.xml'],
  rId5: [REL_TABLE_STYLES, 'tableStyles.xml'],
};

// Content types of the fixed parts (slides are added per slide).
const STATIC_OVERRIDES = {
  [`/${PRESENTATION_PART}`]: CT_PRESENTATION,
  [`/${SLIDE_MASTER_PART}`]: CT_SLIDE_MASTER,
  '/ppt/slideLayouts/slideLayout1.xml': CT_SLIDE_LAYOUT,
  '/ppt/slideLayouts/slideLayout2.xml': CT_SLIDE_LAYOUT,
  '/ppt/slideLayouts/slideLayout3.xml': CT_SLIDE_LAYOUT,
  '/ppt/theme/theme1.xml': CT_THEME,
  '/ppt/presProps.xml': CT_PRES_PROPS,
  '/ppt/viewProps.xml': CT_VIEW_PROPS,
  '/ppt/tableStyles.xml': CT_TABLE_STYLES,
  [`/${CORE_PROPS_PART}`]: CT_CORE_PROPS,
  [`/${APP_PROPS_PART}`]: CT_EXTENDED_PROPS,
  [`/${CUSTOM_PROPS_PART}`]: CT_CUSTOM_PROPS,
};

// Namespace declarations used by the PresentationML templates below.
const XMLNS_PML = `xmlns:a="${NS.a}" xmlns:r="${NS.r}" xmlns:p="${NS.p}"`;

const XML_DECLARATION = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n';

// Templates below hold {name} slots, filled by fill() in common.js.

const ROOT_RELS_XML = `<Relationships xmlns="${NS.rel}">`
  + `<Relationship Id="rId1" Type="${REL_OFFICE_DOCUMENT}" Target="${PRESENTATION_PART}"/>`
  + `<Relationship Id="rId2" Type="${REL_CORE_PROPS}" Target="${CORE_PROPS_PART}"/>`
  + `<Relationship Id="rId3" Type="${REL_EXTENDED_PROPS}" Target="${APP_PROPS_PART}"/>`
  + `<Relationship Id="rId4" Type="${REL_CUSTOM_PROPS}" Target="${CUSTOM_PROPS_PART}"/>`
  + '</Relationships>';

const APP_PROPS_XML = `<Properties xmlns="${NS.app}" xmlns:vt="${NS.vt}">`
  + `<Application>${APP_NAME}</Application>`
  + '<PresentationFormat>Widescreen</PresentationFormat>'
  + '<AppVersion>16.0000</AppVersion>'
  + '</Properties>';

// {title} and {now} (W3CDTF) are filled when the package is built.
const CORE_PROPS_XML = '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
  + 'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
  + 'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
  + `<dc:title>{title}</dc:title><dc:creator>${APP_NAME}</dc:creator>`
  + '<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
  + '<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
  + '</cp:coreProperties>';

// The chosen layout patterns ({json}, XML-escaped) travel with the package here, not in the markdown.
const LAYOUTS_PROPERTY = `${APP_NAME} layouts`;
const CUSTOM_PROPS_XML = `<Properties xmlns="${NS.custom}" xmlns:vt="${NS.vt}">`
  + '<property fmtid="{D5CDD505-2E9C-101B-9397-08002B2CF9AE}" pid="2" '
  + `name="${LAYOUTS_PROPERTY}"><vt:lpwstr>{json}</vt:lpwstr></property></Properties>`;

// p:sldIdLst is (re)built from the deck's slide order when the package is written.
const PRESENTATION_XML = `<p:presentation ${XMLNS_PML} saveSubsetFonts="1">`
  + '<p:sldMasterIdLst><p:sldMasterId id="2147483648" r:id="rId1"/></p:sldMasterIdLst>'
  + `<p:sldSz cx="${SLIDE_W}" cy="${SLIDE_H}"/>`
  + `<p:notesSz cx="${NOTES_W}" cy="${NOTES_H}"/>`
  + '<p:defaultTextStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr></p:defaultTextStyle>'
  + '</p:presentation>';

// Children of p:presentation that must come before p:sldIdLst.
const PRESENTATION_BEFORE_SLIDES = ['sldMasterIdLst', 'notesMasterIdLst', 'handoutMasterIdLst'];

const PRES_PROPS_XML = `<p:presentationPr ${XMLNS_PML}/>`;

const VIEW_PROPS_XML = `<p:viewPr ${XMLNS_PML}>`
  + '<p:normalViewPr><p:restoredLeft sz="15620"/><p:restoredTop sz="94660"/></p:normalViewPr>'
  + '<p:gridSpacing cx="76200" cy="76200"/>'
  + '</p:viewPr>';

const TABLE_STYLES_XML = `<a:tblStyleLst xmlns:a="${NS.a}" def="{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}"/>`;

// Theme fonts (Latin and East Asian).
const THEME_FONT = 'Yu Gothic';

const THEME_FONT_XML = `<a:latin typeface="${THEME_FONT}"/><a:ea typeface="${THEME_FONT}"/><a:cs typeface=""/>`
  + `<a:font script="Jpan" typeface="${THEME_FONT}"/>`;
const PH_FILL = '<a:solidFill><a:schemeClr val="phClr"/></a:solidFill>';

const THEME_XML = `<a:theme xmlns:a="${NS.a}" name="${APP_NAME}">`
  + '<a:themeElements>'
  + `<a:clrScheme name="${APP_NAME}">`
  + '<a:dk1><a:sysClr val="windowText" lastClr="000000"/></a:dk1>'
  + '<a:lt1><a:sysClr val="window" lastClr="FFFFFF"/></a:lt1>'
  + '<a:dk2><a:srgbClr val="1F2937"/></a:dk2><a:lt2><a:srgbClr val="E7E6E6"/></a:lt2>'
  + '<a:accent1><a:srgbClr val="1F6FEB"/></a:accent1><a:accent2><a:srgbClr val="ED7D31"/></a:accent2>'
  + '<a:accent3><a:srgbClr val="A5A5A5"/></a:accent3><a:accent4><a:srgbClr val="FFC000"/></a:accent4>'
  + '<a:accent5><a:srgbClr val="5B9BD5"/></a:accent5><a:accent6><a:srgbClr val="70AD47"/></a:accent6>'
  + '<a:hlink><a:srgbClr val="0563C1"/></a:hlink><a:folHlink><a:srgbClr val="954F72"/></a:folHlink>'
  + '</a:clrScheme>'
  + `<a:fontScheme name="${APP_NAME}"><a:majorFont>${THEME_FONT_XML}</a:majorFont>`
  + `<a:minorFont>${THEME_FONT_XML}</a:minorFont></a:fontScheme>`
  + `<a:fmtScheme name="${APP_NAME}">`
  + `<a:fillStyleLst>${PH_FILL.repeat(3)}</a:fillStyleLst>`
  + `<a:lnStyleLst>${`<a:ln w="6350">${PH_FILL}</a:ln>`.repeat(3)}</a:lnStyleLst>`
  + `<a:effectStyleLst>${'<a:effectStyle><a:effectLst/></a:effectStyle>'.repeat(3)}</a:effectStyleLst>`
  + `<a:bgFillStyleLst>${PH_FILL.repeat(3)}</a:bgFillStyleLst>`
  + '</a:fmtScheme>'
  + '</a:themeElements>'
  + '<a:objectDefaults/><a:extraClrSchemeLst/>'
  + '</a:theme>';

const GROUP_PROPS = '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
  + '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
  + '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>';
const TEXT_COLOR_XML = '<a:solidFill><a:schemeClr val="tx1"/></a:solidFill>';

// Placeholder frames (x, y, cx, cy) of the slide master.
const NORMAL_TITLE_FRAME = [838200, 365125, 10515600, 1325563];
const NORMAL_BODY_FRAME = [838200, 1825625, 10515600, 4351338];

// Title font size (1/100 pt) of the slide master.
const TITLE_SIZE = 4000;

// One level of the master's p:bodyStyle ({n} = 1-based level; marL grows per level).
const BODY_LEVEL_XML = '<a:lvl{n}pPr marL="{margin}" indent="-{hang}" algn="l" '
  + 'defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
  + '<a:lnSpc><a:spcPct val="90000"/></a:lnSpc><a:spcBef><a:spcPts val="1000"/></a:spcBef>'
  + `<a:buFont typeface="${BULLET_FONT}"/><a:buChar char="${BULLET_CHAR}"/>`
  + `<a:defRPr sz="{size}" kern="1200">${TEXT_COLOR_XML}`
  + '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr>'
  + '</a:lvl{n}pPr>';

// Placeholder shape with a frame; used by the master and the layouts.
const PH_SHAPE = '<p:sp><p:nvSpPr><p:cNvPr id="{id}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
  + '<p:nvPr><p:ph {ph}/></p:nvPr></p:nvSpPr>'
  + '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
  + '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
  + '<p:txBody><a:bodyPr vert="horz" lIns="91440" tIns="45720" rIns="91440" bIns="45720" rtlCol="0" anchor="{anchor}">'
  + '<a:normAutofit/></a:bodyPr>{lst}<a:p><a:r><a:rPr lang="en-US"/><a:t>{prompt}</a:t></a:r></a:p></p:txBody></p:sp>';

// Title and body shapes of the slide master.
const MASTER_TEXT_SHAPES = [
  { id: 2, name: 'Title Placeholder 1', ph: 'type="title"', anchor: 'ctr', prompt: 'Click to edit Master title style', frame: NORMAL_TITLE_FRAME },
  { id: 3, name: 'Text Placeholder 2', ph: 'type="body" idx="1"', anchor: 't', prompt: 'Click to edit Master text styles', frame: NORMAL_BODY_FRAME },
];

// Date, footer text and slide number shapes: frames are (x, y, cx, cy) in EMU. The same shape
// ids are used on the master and the layouts; slides refer to them through the p:ph attributes.
const FOOTER_DATE = 'dt';
const FOOTER_TEXT = 'ftr';
const FOOTER_NUMBER = 'sldNum';
const FOOTER_Y = 6356350;
const FOOTER_H = 365125;
const FOOTER_PLACEHOLDERS = {
  dt: {
    id: 4, name: 'Date Placeholder', ph: { type: 'dt', sz: 'half', idx: '10' },
    master_ph: 'type="dt" sz="half" idx="2"', frame: [838200, FOOTER_Y, 2743200, FOOTER_H], align: 'l',
  },
  ftr: {
    id: 5, name: 'Footer Placeholder', ph: { type: 'ftr', sz: 'quarter', idx: '11' },
    master_ph: 'type="ftr" sz="quarter" idx="3"', frame: [4038600, FOOTER_Y, 4114800, FOOTER_H], align: 'ctr',
  },
  sldNum: {
    id: 6, name: 'Slide Number Placeholder', ph: { type: 'sldNum', sz: 'quarter', idx: '12' },
    master_ph: 'type="sldNum" sz="quarter" idx="4"', frame: [8610600, FOOTER_Y, 2743200, FOOTER_H], align: 'r',
  },
};

// Fields that PowerPoint keeps current (id, type); the text written with them is only a cached value.
const FOOTER_FIELDS = {
  dt: ['{5B2F0E11-7C3A-4D19-9E21-3A6C1D7F4B01}', 'datetime1'],
  sldNum: ['{8D4A6C22-1E5B-4F37-A842-6B9E2C5D7A02}', 'slidenum'],
};

// Look of the footer shapes on the master and the layouts.
const FOOTER_SIZE = 1200;
const MUTED_COLOR = '595959';

// Footer shape of the master and the layouts ({content} = what the a:p holds).
const FOOTER_SHAPE = '<p:sp><p:nvSpPr><p:cNvPr id="{id}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
  + '<p:nvPr><p:ph {ph}/></p:nvPr></p:nvSpPr>'
  + '<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
  + '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr>'
  + '<p:txBody><a:bodyPr vert="horz" lIns="91440" tIns="45720" rIns="91440" bIns="45720" rtlCol="0" anchor="ctr"/>'
  + `<a:lstStyle><a:lvl1pPr algn="{align}"><a:defRPr sz="${FOOTER_SIZE}">`
  + `<a:solidFill><a:srgbClr val="${MUTED_COLOR}"/></a:solidFill></a:defRPr></a:lvl1pPr></a:lstStyle>`
  + '<a:p>{content}</a:p></p:txBody></p:sp>';

// Footer contents on the master and the layouts ({text} = the footer text as runs).
const FOOTER_FIELD_XML = '<a:fld id="{id}" type="{type}"><a:rPr lang="en-US"/><a:t>{text}</a:t></a:fld>';
const FOOTER_RUN_XML = '<a:r><a:rPr lang="en-US"/><a:t>{text}</a:t></a:r>';
const FOOTER_EMPTY_XML = '<a:endParaRPr lang="en-US"/>';
const FOOTER_NUMBER_SAMPLE = '‹#›';
const FOOTER_DATE_SAMPLE = '1/1/2026';

// {shapes} = the master's placeholder shapes, {body_levels} = its p:bodyStyle levels.
const SLIDE_MASTER_XML = `<p:sldMaster ${XMLNS_PML}><p:cSld><p:bg><p:bgRef idx="1001"><a:schemeClr val="bg1"/></p:bgRef></p:bg>`
  + `<p:spTree>${GROUP_PROPS}{shapes}</p:spTree></p:cSld>`
  + '<p:clrMap bg1="lt1" tx1="dk1" bg2="lt2" tx2="dk2" accent1="accent1" accent2="accent2" accent3="accent3" '
  + 'accent4="accent4" accent5="accent5" accent6="accent6" hlink="hlink" folHlink="folHlink"/>'
  + '<p:sldLayoutIdLst><p:sldLayoutId id="2147483649" r:id="rId1"/><p:sldLayoutId id="2147483650" r:id="rId2"/>'
  + '<p:sldLayoutId id="2147483651" r:id="rId4"/></p:sldLayoutIdLst>'
  + '<p:txStyles>'
  + '<p:titleStyle><a:lvl1pPr algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
  + '<a:lnSpc><a:spcPct val="90000"/></a:lnSpc><a:spcBef><a:spcPct val="0"/></a:spcBef><a:buNone/>'
  + `<a:defRPr sz="${TITLE_SIZE}" kern="1200">${TEXT_COLOR_XML}`
  + '<a:latin typeface="+mj-lt"/><a:ea typeface="+mj-ea"/><a:cs typeface="+mj-cs"/></a:defRPr>'
  + '</a:lvl1pPr></p:titleStyle>'
  + '<p:bodyStyle>{body_levels}</p:bodyStyle>'
  + '<p:otherStyle><a:defPPr><a:defRPr lang="en-US"/></a:defPPr>'
  + '<a:lvl1pPr marL="0" algn="l" defTabSz="914400" rtl="0" eaLnBrk="1" latinLnBrk="0" hangingPunct="1">'
  + `<a:defRPr sz="1800" kern="1200">${TEXT_COLOR_XML}`
  + '<a:latin typeface="+mn-lt"/><a:ea typeface="+mn-ea"/><a:cs typeface="+mn-cs"/></a:defRPr></a:lvl1pPr>'
  + '</p:otherStyle>'
  + '</p:txStyles></p:sldMaster>';

const SLIDE_MASTER_RELS = {
  rId1: [REL_SLIDE_LAYOUT, '../slideLayouts/slideLayout1.xml'],
  rId2: [REL_SLIDE_LAYOUT, '../slideLayouts/slideLayout2.xml'],
  rId3: [REL_THEME, '../theme/theme1.xml'],
  rId4: [REL_SLIDE_LAYOUT, '../slideLayouts/slideLayout3.xml'],
};

// One slide layout; shapes and attributes are filled from the chosen pattern.
const SLIDE_LAYOUT_XML = `<p:sldLayout ${XMLNS_PML} type="{type}" preserve="1"><p:cSld name="{name}">{background}<p:spTree>${GROUP_PROPS}`
  + '{title_shape}{body_shape}{footer_shapes}'
  + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>';

// Background of a layout: a solid color, or an image stretched over the slide. Slides inherit it.
const BACKGROUND_COLOR_XML = '<p:bg><p:bgPr><a:solidFill><a:srgbClr val="{color}"/></a:solidFill><a:effectLst/></p:bgPr></p:bg>';
const BACKGROUND_IMAGE_XML = '<p:bg><p:bgPr><a:blipFill dpi="0" rotWithShape="1"><a:blip r:embed="{rid}"/><a:srcRect/>'
  + '<a:stretch><a:fillRect/></a:stretch></a:blipFill><a:effectLst/></p:bgPr></p:bg>';

// Id of the background image's relationship in a layout part (rId1 is its master).
const LAYOUT_IMAGE_RID = 'rId2';

// p:sldLayout@type, display name and prompt texts of the layout per slide kind.
const SLIDE_LAYOUT_INFO = {
  normal: { type: 'obj', name: 'Title and Content', title_prompt: 'Title', body_prompt: 'Text' },
  chapter: { type: 'secHead', name: 'Section Header', title_prompt: 'Chapter title', body_prompt: 'Note' },
  title: { type: 'title', name: 'Title Slide', title_prompt: 'Title', body_prompt: 'Subtitle' },
};

const SLIDE_LAYOUT_RELS = { rId1: [REL_SLIDE_MASTER, '../slideMasters/slideMaster1.xml'] };

// Fixed parts of a new package: path -> XML (the master and the layouts are built separately,
// relationship parts are listed separately).
const STATIC_PARTS = {
  [APP_PROPS_PART]: APP_PROPS_XML,
  'ppt/presProps.xml': PRES_PROPS_XML,
  'ppt/viewProps.xml': VIEW_PROPS_XML,
  'ppt/tableStyles.xml': TABLE_STYLES_XML,
  'ppt/theme/theme1.xml': THEME_XML,
};

// Relationship parts of the fixed parts: path -> {id: [type, target]}.
const STATIC_RELS = {
  'ppt/slideMasters/_rels/slideMaster1.xml.rels': SLIDE_MASTER_RELS,
  'ppt/slideLayouts/_rels/slideLayout1.xml.rels': SLIDE_LAYOUT_RELS,
  'ppt/slideLayouts/_rels/slideLayout2.xml.rels': SLIDE_LAYOUT_RELS,
  'ppt/slideLayouts/_rels/slideLayout3.xml.rels': SLIDE_LAYOUT_RELS,
};

// A new slide: title and body placeholders ({title_ph} / {body_ph} = p:ph attributes), text filled later.
const SLIDE_XML = `<p:sld ${XMLNS_PML}><p:cSld><p:spTree>${GROUP_PROPS}`
  + '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Title 1"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
  + '<p:nvPr><p:ph {title_ph}/></p:nvPr></p:nvSpPr><p:spPr/>'
  + '<p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/></p:txBody></p:sp>'
  + '<p:sp><p:nvSpPr><p:cNvPr id="3" name="Content Placeholder 2"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
  + '<p:nvPr><p:ph {body_ph}/></p:nvPr></p:nvSpPr><p:spPr/>'
  + '<p:txBody><a:bodyPr><a:normAutofit/></a:bodyPr><a:lstStyle/></p:txBody></p:sp>'
  + '</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>';

// A date, footer text or slide number shape on a slide; placed by its layout, text filled later.
const SLIDE_FOOTER_SHAPE = `<p:sp ${XMLNS_PML}><p:nvSpPr><p:cNvPr id="{id}" name="{name}"/><p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>`
  + '<p:nvPr><p:ph {ph}/></p:nvPr></p:nvSpPr><p:spPr/>'
  + '<p:txBody><a:bodyPr/><a:lstStyle/></p:txBody></p:sp>';

// --- layouts ---
// App-side look of the slides; never written to the markdown. For each slide kind one placement
// pattern is chosen, and each text type (title and body block types) is specified directly.
// Reading slides back must not rely on any text property: plain text and sub headings differ by
// paragraph level.

const LAYOUT_PATTERNS = ['a', 'b', 'c'];
const DEFAULT_LAYOUT_PATTERN = 'a';

// What a pattern is chosen for.
const SLOT_SLIDE = 'slide';
const SLOT_TITLE = 'title';
const SLOT_FOOTER = 'footer';
const LAYOUT_SLOTS = [SLOT_SLIDE];

// Text types that are specified directly, in display order.
const TEXT_SLOTS = [SLOT_TITLE, BLOCK_PARA, BLOCK_HEADING, BLOCK_BULLET, BLOCK_NUMBER, SLOT_FOOTER];

// Row labels of the layout dialog, by text type.
const TEXT_SLOT_LABELS = {
  title: 'Title',
  para: 'Body',
  heading: 'Subheading',
  bullet: 'Bullet',
  number: 'Number',
  footer: 'Footer',
};

// Paragraph level (a:pPr@lvl) telling apart the two block types without a bullet.
const HEADING_PARA_LEVEL = '0';
const PLAIN_PARA_LEVEL = '1';

// Fonts offered for text types (not embedded in the PPTX: the viewing PC must have them).
// Keep null out of this list; null means the theme font.
const FONT_CHOICES = [
  'Yu Gothic', 'Yu Mincho', 'Meiryo', 'Meiryo UI', 'BIZ UDPGothic', 'BIZ UDPMincho',
  'MS PGothic', 'MS PMincho', 'Arial', 'Times New Roman',
];

// Sizes offered (1/100 pt), and bullet glyphs and numbering schemes (id -> how it looks).
const FONT_SIZE_CHOICES = [1200, 1400, 1600, 1800, 2000, 2400, 2800, 3200, 3600, 4000, 4800, 5400, 6000, 7200];
const BULLET_CHOICES = [BULLET_CHAR, '■', '–', '→'];
const SCHEME_PAREN = 'arabicParenR';
const SCHEME_CIRCLE = 'circleNumDbPlain';
const NUMBER_SCHEMES = { [NUMBER_SCHEME]: '1.', [SCHEME_PAREN]: '1)', [SCHEME_CIRCLE]: '①' };

// A text type's look when nothing says otherwise. size null = the base size of the slide kind
// (titles: of the placement pattern); color null = the theme text color; font null = the theme font.
const TEXT_STYLE_DEFAULTS = { font: null, size: null, bold: false, italic: false, underline: false, color: null };

// Background and footer of a slide kind when nothing says otherwise. bg_color null = the theme
// background; bg_image (a name from Deck.images) is used instead of bg_color when set.
const DESIGN_DEFAULTS = { bg_color: null, bg_image: null, footer_text: '', show_number: false, show_date: false };

// Placement per slide kind and pattern: frames are (x, y, cx, cy) in EMU, sizes in 1/100 pt,
// aligns "l" / "ctr", anchors "t" / "ctr" / "b".
const SLIDE_LAYOUTS = {
  title: {
    a: {
      label: 'Centered', title_frame: [1524000, 1122363, 9144000, 2387600], body_frame: [1524000, 3602038, 9144000, 1655762],
      title_size: 6000, title_align: 'ctr', title_anchor: 'b', body_align: 'ctr',
    },
    b: {
      label: 'Left-aligned', title_frame: [838200, 1371600, 10515600, 2286000], body_frame: [838200, 3733800, 10515600, 1524000],
      title_size: 5400, title_align: 'l', title_anchor: 'b', body_align: 'l',
    },
    c: {
      label: 'Low', title_frame: [838200, 3200400, 10515600, 1905000], body_frame: [838200, 5181600, 10515600, 990600],
      title_size: 4800, title_align: 'l', title_anchor: 'b', body_align: 'l',
    },
  },
  chapter: {
    a: {
      label: 'Bottom left', title_frame: [831850, 1709738, 10515600, 2852737], body_frame: [831850, 4589463, 10515600, 1500187],
      title_size: 5400, title_align: 'l', title_anchor: 'b', body_align: 'l',
    },
    b: {
      label: 'Centered', title_frame: [1524000, 1709738, 9144000, 2387600], body_frame: [1524000, 4191000, 9144000, 1500187],
      title_size: 5400, title_align: 'ctr', title_anchor: 'b', body_align: 'ctr',
    },
    c: {
      label: 'High', title_frame: [838200, 838200, 10515600, 1828800], body_frame: [838200, 2743200, 10515600, 3200400],
      title_size: 4800, title_align: 'l', title_anchor: 't', body_align: 'l',
    },
  },
  normal: {
    a: {
      label: 'Title on top', title_frame: [838200, 365125, 10515600, 1325563], body_frame: [838200, 1825625, 10515600, 4351338],
      title_size: 4000, title_align: 'l', title_anchor: 'ctr', body_align: 'l',
    },
    b: {
      label: 'Centered title', title_frame: [838200, 365125, 10515600, 1325563], body_frame: [1524000, 1825625, 9144000, 4351338],
      title_size: 3600, title_align: 'ctr', title_anchor: 'ctr', body_align: 'l',
    },
    c: {
      label: 'Side by side', title_frame: [609600, 1371600, 3505200, 4114800], body_frame: [4419600, 685800, 7162800, 5486400],
      title_size: 3200, title_align: 'l', title_anchor: 'ctr', body_align: 'l',
    },
  },
};

// Base body text size (1/100 pt) per list level and slide kind. A size chosen in the app replaces
// level 0; deeper levels keep their ratio to it.
const BODY_SIZES = {
  title: new Array(MAX_LEVEL + 1).fill(2400),
  chapter: new Array(MAX_LEVEL + 1).fill(2400),
  normal: BODY_LEVEL_SIZES,
};

const BASE_TEXT_DEFAULTS = {
  title: {},
  para: {},
  heading: { bold: true },
  bullet: { char: BULLET_CHAR },
  number: { scheme: NUMBER_SCHEME },
  footer: { size: FOOTER_SIZE, color: MUTED_COLOR },
};

// Defaults per slide kind and text type, on top of TEXT_STYLE_DEFAULTS.
const TEXT_DEFAULTS = {
  title: BASE_TEXT_DEFAULTS,
  chapter: { ...BASE_TEXT_DEFAULTS, para: { color: MUTED_COLOR } },
  normal: BASE_TEXT_DEFAULTS,
};

// --- screen ---

// Largest number with a circled glyph, and the code point of the circled 1.
const MAX_CIRCLED = 20;
const CIRCLED_ONE = 0x2460;

// Align / anchor values of the layout patterns as CSS.
const ALIGN_CSS = { l: 'left', ctr: 'center', r: 'right' };
const ANCHOR_CSS = { t: 'flex-start', ctr: 'center', b: 'flex-end' };

// Color shown for a slide that uses the theme background.
const THEME_BACKGROUND_COLOR = 'FFFFFF';

// Sample shown in the layout preview: one line of every text type, named after that type.
// Title and chapter slides have a small body area, so they show fewer lines.
const PREVIEW_TITLE = 'Title';
const PREVIEW_NUMBER = 1;
const PREVIEW_SHORT_BLOCKS = [
  { type: BLOCK_HEADING, level: 0, text: 'Subheading' },
  { type: BLOCK_PARA, level: 0, text: 'Body text' },
  { type: BLOCK_BULLET, level: 0, text: 'Bullet' },
  { type: BLOCK_NUMBER, level: 0, text: 'Numbered' },
];
const PREVIEW_BLOCKS = {
  title: PREVIEW_SHORT_BLOCKS,
  chapter: PREVIEW_SHORT_BLOCKS,
  normal: [
    { type: BLOCK_HEADING, level: 0, text: 'Subheading' },
    { type: BLOCK_PARA, level: 0, text: 'Body text' },
    { type: BLOCK_BULLET, level: 0, text: 'Bullet' },
    { type: BLOCK_BULLET, level: 1, text: 'Nested bullet' },
    { type: BLOCK_NUMBER, level: 0, text: 'Numbered' },
    { type: BLOCK_NUMBER, level: 0, text: 'Numbered' },
  ],
};

// Toggle buttons of the layout dialog: pattern property -> button text.
const STYLE_TOGGLES = { bold: 'B', italic: 'I', underline: 'U' };

// Color shown for text that uses the theme color.
const THEME_TEXT_COLOR = '000000';

// Font stack behind a chosen font, and on slides using the theme font.
const FONT_FALLBACK = 'sans-serif';

// Slide width in points (13.333 in); font sizes are drawn relative to it.
const SLIDE_W_PT = 960;

// Quiet time (ms) after typing before an edit is written into the slides / markdown.
const MD_SYNC_DELAY = 250;
const SLIDE_SYNC_DELAY = 400;

// How long a notice stays visible (ms).
const NOTICE_DURATION = 4000;

// Markdown highlight colors by token class (see highlightLine in common.js).
const MD_COLORS = {
  h1: '#b42318',
  h2: '#1d4ed8',
  h3: '#047857',
  h4: '#7c3aed',
  marker: '#c2410c',
  escape: '#9ca3af',
  text: '#1f2937',
};

// Editor font, shared by the textarea and the highlight layer so both line up.
const EDITOR_FONT = '14px/1.6 Consolas, "BIZ UDGothic", "MS Gothic", monospace';

// Style of the two editor layers: a transparent textarea over a highlighted copy of the same text.
const EDITOR_LAYER = {
  position: 'absolute', inset: 0, width: '100%', height: '100%', margin: 0, padding: '12px 16px',
  font: EDITOR_FONT, whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', tabSize: 4,
  overflowY: 'scroll', border: 'none', boxSizing: 'border-box',
};

// Style of the empty slide surface shared by the slide editor and the layout preview.
const SLIDE_SURFACE = {
  position: 'relative', width: '100%', aspectRatio: `${SLIDE_W} / ${SLIDE_H}`, containerType: 'inline-size',
  bgcolor: '#fff', border: '1px solid #d0d5dd', boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  fontFamily: '"Yu Gothic", "Meiryo", sans-serif', color: '#111',
};
