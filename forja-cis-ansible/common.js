async function api(path, params) {
  const query = params ? '?' + new URLSearchParams(params).toString() : '';
  return parseResponse(await fetch(API_BASE + path + query));
}

async function apiPost(path, body) {
  return parseResponse(await fetch(API_BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }));
}

async function parseResponse(res) {
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* not JSON */ }
    throw new Error(`${res.status} ${detail}`);
  }
  return res.json();
}

// Keep items whose number or title contains every word of the query.
// Sections are kept when one of their recommendations matches.
function filterItems(items, query) {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return items;
  const hit = (item) => {
    const text = `${item.number} ${item.title}`.toLowerCase();
    return words.every((w) => text.includes(w));
  };
  const matched = items.filter((i) => i.kind === 'recommendation' && hit(i));
  return items.filter((i) =>
    i.kind === 'recommendation'
      ? matched.includes(i)
      : hit(i) || matched.some((r) => r.number.startsWith(i.number + '.'))
  );
}

// true when GET /health answers {"status": "ok"}; false on any network or HTTP error.
async function checkHealth() {
  try {
    const res = await fetch(API_BASE + '/health', { cache: 'no-store' });
    return res.ok && (await res.json()).status === 'ok';
  } catch (e) {
    return false;
  }
}
