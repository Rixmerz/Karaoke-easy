/* Duelo por turnos: lógica pura (sin DOM), para poder probarla con node. */
const DuelLogic = {
  // players: [{name, mic}], pool: [songId], mode: "same" (todos cantan la misma canción en cada ronda)
  // o "each" (cada jugador una canción distinta). first: canción elegida para la primera ronda.
  makeTurns(players, pool, mode, rounds, first, rnd = Math.random) {
    const bag = [];
    const draw = avoid => { // saca canciones sin repetir hasta agotar la lista, luego vuelve a empezar
      if (!pool.length) return null;
      if (!bag.length) { bag.push(...pool); for (let i = bag.length - 1; i > 0; i--) { const j = rnd() * (i + 1) | 0; [bag[i], bag[j]] = [bag[j], bag[i]]; } }
      let k = bag.findIndex(x => !avoid.has(x)); if (k < 0) k = 0;
      return bag.splice(k, 1)[0];
    };
    const used = new Set(first ? [first] : []), turns = [];
    for (let r = 0; r < rounds; r++) {
      if (mode === "same") {
        const song = r === 0 && first ? first : draw(used); used.add(song);
        players.forEach((p, i) => turns.push({ round: r, player: i, song }));
      } else {
        players.forEach((p, i) => { const song = r === 0 && i === 0 && first ? first : draw(used); used.add(song); turns.push({ round: r, player: i, song }); });
      }
    }
    return turns;
  },
  // scores: por jugador, lista de porcentajes (uno por turno). Devuelve el ranking ordenado.
  ranking(players, scores) {
    const rows = players.map((p, i) => {
      const s = scores[i] || [], total = s.reduce((a, b) => a + b, 0);
      return { i, name: p.name, total, avg: s.length ? Math.round(total / s.length) : 0, turns: s.length, best: s.length ? Math.max(...s) : 0 };
    });
    rows.sort((a, b) => b.avg - a.avg || b.best - a.best || a.i - b.i);
    let place = 0;
    rows.forEach((r, k) => { if (k === 0 || r.avg !== rows[k - 1].avg || r.best !== rows[k - 1].best) place = k + 1; r.place = place; });
    return rows;
  },
};
if (typeof module !== "undefined") module.exports = DuelLogic;
