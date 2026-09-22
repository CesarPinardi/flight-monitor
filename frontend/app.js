const DATA_URLS = ["data.json", "../data/public/data.json", "data/public/data.json"];
const state = { data: null };

const $ = (id) => document.getElementById(id);
const finite = (value) => typeof value === "number" && Number.isFinite(value);
const array = (value) => Array.isArray(value) ? value : [];

function clear(element) {
  while (element.firstChild) element.removeChild(element.firstChild);
}

function addText(parent, tag, value, className) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  element.textContent = value == null ? "" : String(value);
  parent.append(element);
  return element;
}

function routeKey(route) {
  if (!route || typeof route !== "object") return "";
  return `${route.origin || "?"}-${route.destination || "?"}`;
}

function routeLabel(route) {
  if (!route || typeof route !== "object") return "";
  const outbound = `${route.origin || "?"} → ${route.destination || "?"}`;
  const returnLeg = route.return_origin && route.return_destination
    ? ` · volta ${route.return_origin} → ${route.return_destination}`
    : "";
  return `${outbound}${returnLeg}`;
}

function currency(value, code = "BRL") {
  if (!finite(value)) return "—";
  const normalized = typeof code === "string" && /^[A-Z]{3}$/i.test(code) ? code.toUpperCase() : "BRL";
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: normalized }).format(value);
}

function date(value, withTime = true) {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "—";
  const options = withTime
    ? { dateStyle: "short", timeStyle: "short", timeZone: state.data?.presentation?.timezone || "America/Sao_Paulo" }
    : { dateStyle: "short", timeZone: state.data?.presentation?.timezone || "America/Sao_Paulo" };
  return new Intl.DateTimeFormat("pt-BR", options).format(parsed);
}

function dateOnly(value) {
  if (!value) return "—";
  const [year, month, day] = String(value).split("-");
  return year && month && day ? `${day}/${month}/${year}` : String(value);
}

function money(offer) {
  return offer?.price ? currency(offer.price.amount, offer.price.currency) : "—";
}

function stops(offer) {
  const value = offer?.itinerary?.stops;
  return Number.isInteger(value) && value >= 0 ? value : Math.max(0, array(offer?.itinerary?.segments).length - 1);
}

function stopsLabel(value) {
  if (value === 0) return "Direto";
  if (value === 1) return "1 escala";
  return `${value} escalas`;
}

function durationLabel(minutes) {
  if (!Number.isInteger(minutes) || minutes < 0) return "Duração não informada";
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return hours ? `${hours}h${remaining ? ` ${remaining}min` : ""}` : `${remaining}min`;
}

function airlines(offer) {
  return [...new Set(array(offer?.itinerary?.segments).map((segment) => segment?.airline).filter(Boolean))];
}

function isComparable(offer) {
  return offer?.status === "complete" && offer?.comparison_eligible === true && finite(offer?.price?.amount);
}

function statusInfo(value) {
  const statuses = {
    success: ["success", "Atualizado"],
    complete: ["complete", "Confirmado"],
    stale_data: ["stale", "Dado antigo"],
    quota: ["quota", "Cota atingida"],
    failure: ["failure", "Falha"],
    pending: ["pending", "Incompleto"],
  };
  return statuses[value] || ["unknown", "Sem status"];
}

function statusPill(value) {
  const [className, label] = statusInfo(value);
  const pill = document.createElement("span");
  pill.className = `pill status-${className}`;
  pill.textContent = label;
  return pill;
}

function bestOffer(offers) {
  return array(offers).filter(isComparable).sort((left, right) => left.price.amount - right.price.amount)[0] || null;
}

function setStatus(value, detail = "") {
  const badge = $("status-badge");
  const [className, label] = statusInfo(value);
  badge.className = `status-badge status-${className}`;
  badge.textContent = label;
  $("data-alert").hidden = !detail;
  $("data-alert").textContent = detail;
}

function renderSearch(search) {
  const target = $("search-config");
  clear(target);
  const adults = Number(search?.adults) || 0;
  const children = Number(search?.children) || 0;
  const infants = Number(search?.infants_on_lap) || 0;
  const passengers = [`${adults} adulto${adults === 1 ? "" : "s"}`];
  if (children) passengers.push(`${children} criança${children === 1 ? "" : "s"}`);
  if (infants) passengers.push(`${infants} bebê${infants === 1 ? "" : "s"} no colo`);
  const itineraries = array(search?.itineraries).map((item) => {
    const outbound = item?.outbound || {};
    const returnLeg = item?.return || {};
    return `${outbound.origin || "?"} → ${outbound.destination || "?"} / ${returnLeg.origin || "?"} → ${returnLeg.destination || "?"}`;
  });
  const values = [
    ["Ida", dateOnly(search?.departure_date)],
    ["Volta", dateOnly(search?.return_date)],
    ["Origens", array(search?.origins).join(", ") || "Não informadas"],
    ["Destinos", array(search?.destinations).join(", ") || "Não informados"],
    ...(itineraries.length ? [["Itinerários", itineraries.join("; ")]] : []),
    ["Passageiros", passengers.join(", ")],
    ["Cabine", search?.cabin === "economy" ? "Econômica" : (search?.cabin || "Não informada")],
    ["Pagamento", search?.payment_type === "cash_only" ? "Somente dinheiro" : (search?.payment_type || "Não informado")],
    ["Moeda", search?.currency || "BRL"],
  ];
  for (const [label, value] of values) {
    const item = document.createElement("div");
    addText(item, "dt", label);
    addText(item, "dd", value);
    target.append(item);
  }
}

function setOptions(select, values, emptyLabel) {
  while (select.options.length > 1) select.remove(1);
  select.options[0].textContent = emptyLabel;
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.append(option);
  }
}

function renderFilters(offers) {
  const routes = [...new Set(array(offers).map((offer) => routeLabel(offer.route)).filter(Boolean))].sort();
  const companies = [...new Set(array(offers).flatMap(airlines))].sort();
  setOptions($("route-filter"), routes, "Todas as rotas");
  setOptions($("airline-filter"), companies, "Todas as companhias");
}

function selectedFilters() {
  return {
    route: $("route-filter").value,
    airline: $("airline-filter").value,
    stops: $("stops-filter").value,
    sort: $("sort-filter").value,
  };
}

function filteredOffers(offers) {
  const filters = selectedFilters();
  const result = array(offers).filter((offer) => {
    if (filters.route && routeLabel(offer.route) !== filters.route) return false;
    if (filters.airline && !airlines(offer).includes(filters.airline)) return false;
    if (filters.stops === "0" && stops(offer) !== 0) return false;
    if (filters.stops === "1" && stops(offer) !== 1) return false;
    if (filters.stops === "2" && stops(offer) < 2) return false;
    return true;
  });
  return result.sort((left, right) => {
    if (filters.sort === "duration") return (left.itinerary?.total_duration_minutes ?? Infinity) - (right.itinerary?.total_duration_minutes ?? Infinity);
    if (filters.sort === "stops") return stops(left) - stops(right) || (left.price?.amount ?? Infinity) - (right.price?.amount ?? Infinity);
    return (left.price?.amount ?? Infinity) - (right.price?.amount ?? Infinity);
  });
}

function renderMetrics(offers) {
  const best = bestOffer(offers);
  $("best-price").textContent = best ? money(best) : "—";
  $("best-price-detail").textContent = best ? `${routeLabel(best.route)} · ${airlines(best).join(", ") || "Companhia não informada"}` : "Nenhuma oferta completa publicada.";
  $("offer-count").textContent = String(offers.length);
  $("offer-count-detail").textContent = `${offers.filter(isComparable).length} comparável(is) após filtros.`;

  const history = historyPoints(state.data?.history, selectedFilters().route);
  const lowest = history.filter((point) => finite(point.amount)).sort((left, right) => left.amount - right.amount)[0];
  $("history-price").textContent = lowest ? currency(lowest.amount, lowest.currency) : "—";
  $("history-price-detail").textContent = lowest ? `${routeLabel(lowest.route)} · menor preço diário` : "Histórico sem preço comparável.";
}

function renderOffer(offer) {
  const card = document.createElement("article");
  card.className = "offer-card";
  const top = document.createElement("div");
  top.className = "offer-top";
  const heading = document.createElement("div");
  addText(heading, "div", routeLabel(offer.route), "route-name");
  addText(heading, "div", airlines(offer).join(", ") || "Companhia não informada", "muted");
  top.append(heading, addText(document.createElement("div"), "div", money(offer), "offer-price"));
  card.append(top);
  const meta = document.createElement("div");
  meta.className = "offer-meta";
  addText(meta, "span", stopsLabel(stops(offer)));
  addText(meta, "span", durationLabel(offer.itinerary?.total_duration_minutes));
  addText(meta, "span", offer.price?.includes_taxes === true ? "Taxas incluídas" : "Taxas não confirmadas");
  card.append(meta);
  const bottom = document.createElement("div");
  bottom.className = "offer-bottom";
  if (offer.stale) bottom.append(statusPill("stale"));
  if (!isComparable(offer)) addText(bottom, "span", "Oferta incompleta para comparação", "offer-note");
  const link = offer.links?.google_flights;
  if (typeof link === "string" && /^https:\/\//i.test(link)) {
    const anchor = document.createElement("a");
    anchor.className = "offer-link";
    anchor.href = link;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.textContent = "Abrir fonte";
    bottom.append(anchor);
  }
  card.append(bottom);
  return card;
}

function renderOffers(offers) {
  const target = $("offers");
  clear(target);
  if (!offers.length) {
    addText(target, "p", "Nenhuma oferta atende aos filtros. Tente limpar a seleção.", "empty-state");
    return;
  }
  for (const offer of offers) target.append(renderOffer(offer));
}

function renderRoutes(data) {
  const target = $("routes");
  clear(target);
  const offers = array(data.offers);
  const routeData = data.routes && typeof data.routes === "object" ? data.routes : {};
  const keys = [...new Set([...Object.keys(routeData), ...offers.map((offer) => routeKey(offer.route)).filter(Boolean)])].sort();
  if (!keys.length) {
    const row = document.createElement("tr");
    const cell = addText(row, "td", "Nenhuma rota publicada.");
    cell.colSpan = 4;
    target.append(row);
    return;
  }
  for (const key of keys) {
    const info = routeData[key] || {};
    const routeOffers = offers.filter((offer) => routeKey(offer.route) === key);
    const best = bestOffer(routeOffers);
    const row = document.createElement("tr");
    addText(row, "td", best ? routeLabel(best.route) : key.replace("-", " → "), "route-code");
    const status = document.createElement("td");
    status.append(statusPill(info.stale ? "stale_data" : (info.status || "unknown")));
    row.append(status);
    addText(row, "td", best ? money(best) : "—");
    addText(row, "td", info.last_success_at_utc ? date(info.last_success_at_utc) : "—");
    target.append(row);
  }
}

function historyPoints(history, route) {
  const points = [];
  for (const entry of array(history?.entries)) {
    for (const item of array(entry?.routes)) {
      if (route && routeLabel(item.route) !== route) continue;
      const price = item.minimum_price;
      points.push({
        route: item.route,
        amount: price?.amount,
        currency: price?.currency,
        recordedAt: entry.recorded_at_utc,
        status: item.status,
      });
    }
  }
  return points;
}

function renderHistory(history) {
  $("history-description").textContent = history?.description || "Menor preço diário confirmado por rota. Não é uma oferta específica.";
  const target = $("history");
  clear(target);
  const points = historyPoints(history, selectedFilters().route).filter((point) => finite(point.amount));
  if (!points.length) {
    addText(target, "p", "Ainda não há histórico comparável publicado.", "empty-state");
    return;
  }
  const visible = points.slice(-30);
  const max = Math.max(...visible.map((point) => point.amount));
  for (const point of visible) {
    const row = document.createElement("div");
    row.className = "history-row";
    addText(row, "span", `${date(point.recordedAt, false)} · ${routeLabel(point.route)}`, "history-date");
    const track = document.createElement("div");
    track.className = "history-track";
    const bar = document.createElement("div");
    bar.className = "history-bar";
    bar.style.width = `${Math.max(8, Math.round((point.amount / max) * 100))}%`;
    bar.setAttribute("aria-label", `${currency(point.amount, point.currency)} em ${routeLabel(point.route)}`);
    track.append(bar);
    row.append(track);
    addText(row, "span", currency(point.amount, point.currency), "history-price");
    target.append(row);
  }
}

function render(data) {
  state.data = data;
  renderSearch(data.search || {});
  $("schema-label").textContent = `JSON público · schema ${data.schema_version ?? "?"}`;
  $("last-updated").textContent = data.generated_at_utc ? `Última consulta: ${date(data.generated_at_utc)}` : "Última consulta: não informada";
  const stale = array(data.offers).some((offer) => offer.stale) || data.status === "stale_data";
  const alert = stale ? "Algumas ofertas são dados antigos porque uma ou mais rotas falharam." : (data.status === "failure" ? "Consulta teve falhas. Veja status por rota." : "");
  setStatus(data.status, alert);
  $("disclaimer").textContent = data.disclaimer || "Preço mantém interpretação da fonte. Taxas, bebê de colo, bagagem e inventário não são inferidos.";
  renderFilters(array(data.offers));
  renderRoutes(data);
  updateOffers();
}

function updateOffers() {
  if (!state.data) return;
  const offers = filteredOffers(state.data.offers);
  renderMetrics(offers);
  renderOffers(offers);
  renderHistory(state.data.history);
}

async function loadData() {
  setStatus("pending", "Carregando dados públicos...");
  try {
    let response;
    for (const url of DATA_URLS) {
      const candidate = await fetch(url, { cache: "no-store" });
      if (candidate.ok) { response = candidate; break; }
    }
    if (!response) throw new Error("arquivo público não encontrado");
    const data = await response.json();
    if (!data || typeof data !== "object" || !Array.isArray(data.offers)) throw new Error("formato público inválido");
    render(data);
  } catch (error) {
    state.data = null;
    setStatus("failure", "Não foi possível carregar dados públicos. O painel não inventa preços.");
    $("last-updated").textContent = "Última consulta: arquivo indisponível";
    $("offers").replaceChildren(addText(document.createElement("div"), "p", "Sem dados publicados no momento.", "empty-state"));
    $("history").replaceChildren(addText(document.createElement("div"), "p", "Histórico indisponível.", "empty-state"));
    console.warn("Flight Monitor data load failed", error);
  }
}

for (const id of ["route-filter", "airline-filter", "stops-filter", "sort-filter"]) $(id).addEventListener("change", updateOffers);
$("clear-filters").addEventListener("click", () => {
  $("route-filter").value = "";
  $("airline-filter").value = "";
  $("stops-filter").value = "";
  $("sort-filter").value = "price";
  updateOffers();
});
$("reload").addEventListener("click", loadData);
loadData();
