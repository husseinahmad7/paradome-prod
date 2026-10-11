/** Pure numerical comparison; both runtimes use the pinned q8/tokenizer assets. */
export function compareEmbedding(actual, expected, tolerance) {
  if (actual.length !== expected.length || actual.length !== 384 || !actual.every(Number.isFinite)) return { passed: false, reason: 'dimension or non-finite value' };
  let dot = 0, an = 0, en = 0, difference = 0;
  for (let i = 0; i < actual.length; i++) {
    dot += actual[i] * expected[i]; an += actual[i] ** 2; en += expected[i] ** 2;
    difference = Math.max(difference, Math.abs(actual[i] - expected[i]));
  }
  const cosine = dot / Math.sqrt(an * en);
  return { cosine, maximum_absolute_difference: difference, passed: cosine >= tolerance.minimum_cosine && difference <= tolerance.maximum_absolute_difference };
}

/** Check that numerical drift keeps the same top answer and top-five set. */
export function compareRanking(actual, expected, index) {
  const rank = vector => {
    const norm = Math.hypot(...vector);
    return index.document_ids.map((id, i) => ({ id, score: index.vectors[i].reduce((sum, value, j) => sum + value * vector[j] / norm, 0) }))
      .sort((a, b) => b.score - a.score || a.id.localeCompare(b.id)).slice(0, 5).map(row => row.id);
  };
  const browser = rank(actual), offline = rank(expected);
  const overlap = browser.filter(id => offline.includes(id)).length;
  return { browser, offline, overlap, top_result_agrees: browser[0] === offline[0], passed: browser[0] === offline[0] && overlap === 5 };
}
