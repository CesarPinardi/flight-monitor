const config = [
  ["Ida", "05/03/2027"],
  ["Volta", "14/03/2027"],
  ["Rotas", "GRU/VCP para MCO/FLL/MIA"],
  ["Passageiros", "2 adultos e 1 bebê no colo"],
  ["Cabine", "Econômica"],
  ["Moeda", "BRL"]
];

const target = document.querySelector("#search-config");
for (const [label, value] of config) {
  const term = document.createElement("dt");
  const description = document.createElement("dd");
  term.textContent = label;
  description.textContent = value;
  target.append(term, description);
}
