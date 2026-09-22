const DATA_URLS = ["data.json", "../data/public/data.json", "data/public/data.json"];
const MAX_VISIBLE_OFFERS = 6;
const state = { data: null, showAllOffers: false, selectedOfferIds: new Set() };

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
  const key = `${route.origin || "?"}-${route.destination || "?"}`;
  const leg = route.leg ? `:${route.leg}` : "";
  const returning = route.return_origin && route.return_destination
    ? `:${route.return_origin}-${route.return_destination}`
    : "";
  return `${key}${leg}${returning}`;
}

function legLabel(value) {
  return value === "outbound" ? "Ida" : value === "return" ? "Volta" : value === "package" ? "Pacote ida e volta" : "Ida e volta";
}

function routeLabel(route) {
  if (!route || typeof route !== "object") return "";
  const outbound = `${route.origin || "?"} → ${route.destination || "?"}`;
  if (route.return_origin && route.return_destination) {
    return `${outbound} / ${route.return_origin} → ${route.return_destination} · pacote ida e volta`;
  }
  const leg = route.leg ? ` · ${legLabel(route.leg).toLowerCase()}` : "";
  return `${outbound}${leg}`;
}

function isPackageOffer(offer) {
  const route = offer?.route || {};
  const type = offer?.itinerary?.type;
  return Boolean(route.return_origin && route.return_destination)
    || type === "round_trip"
    || type === "multi_city";
}

function singleLegOffers(offers) {
  return array(offers).filter((offer) => {
    const route = offer?.route || {};
    const type = offer?.itinerary?.type;
    return !route.return_origin && !route.return_destination && type !== "round_trip" && type !== "multi_city";
  });
}

function displayOffers(offers) {
  return array(offers).filter((offer) => singleLegOffers([offer]).length || isPackageOffer(offer));
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

function selectedTotal(offers) {
  const selected = array(offers).filter((offer) => offer?.id && state.selectedOfferIds.has(offer.id) && isComparable(offer));
  if (!selected.length) return null;
  const currencies = [...new Set(selected.map((offer) => {
    const value = offer.price?.currency;
    return typeof value === "string" && /^[A-Z]{3}$/i.test(value) ? value.toUpperCase() : "BRL";
  }))];
  if (currencies.length !== 1) return { count: selected.length, incompatible: true };
  return {
    amount: selected.reduce((total, offer) => total + offer.price.amount, 0),
    count: selected.length,
    currency: currencies[0],
  };
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
  const selectedLeg = search?.trip_leg === "return" ? "return" : "outbound";
  const bothLegs = search?.trip_leg === "both";
  const adults = Number(search?.adults) || 0;
  const children = Number(search?.children) || 0;
  const infants = Number(search?.infants_on_lap) || 0;
  const passengers = [`${adults} adulto${adults === 1 ? "" : "s"}`];
  if (children) passengers.push(`${children} criança${children === 1 ? "" : "s"}`);
  if (infants) passengers.push(`${infants} bebê${infants === 1 ? "" : "s"} no colo`);
  const itineraries = array(search?.itineraries).map((item) => {
    if (bothLegs) {
      const outbound = item?.outbound || {};
      const returning = item?.return || {};
      return `${outbound.origin || "?"} → ${outbound.destination || "?"} / ${returning.origin || "?"} → ${returning.destination || "?"}`;
    }
    const leg = item?.[selectedLeg] || item?.outbound || {};
    return `${leg.origin || "?"} → ${leg.destination || "?"}`;
  });
  const dates = bothLegs
    ? `Ida ${dateOnly(search?.departure_date)} · Volta ${dateOnly(search?.return_date)}`
    : dateOnly(selectedLeg === "return" ? search?.return_date : search?.departure_date);
  const values = [
    ["Trecho", bothLegs ? "Ida e volta" : legLabel(selectedLeg)],
    ["Data", dates],
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

function setOptions(select, values, emptyLabel, label = (value) => value) {
  while (select.options.length > 1) select.remove(1);
  select.options[0].textContent = emptyLabel;
  for (const value of values) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label(value);
    select.append(option);
  }
}

function renderFilters(offers, search = {}) {
  const routes = [...new Set(array(offers).map((offer) => routeLabel(offer.route)).filter(Boolean))].sort();
  const companies = [...new Set(array(offers).flatMap(airlines))].sort();
  const configuredLegs = search.trip_type === "one_way" ? ["outbound", "return"] : [];
  const packageLeg = array(offers).some(isPackageOffer) ? ["package"] : [];
  const availableLegs = [...new Set([...configuredLegs, ...packageLeg, ...array(offers).map((offer) => offer?.route?.leg).filter(Boolean)])];
  const order = ["outbound", "return", "package"];
  const legs = availableLegs.sort((left, right) => (order.indexOf(left) + 1 || 99) - (order.indexOf(right) + 1 || 99));
  setOptions($("route-filter"), routes, "Todas as rotas");
  setOptions($("airline-filter"), companies, "Todas as companhias");
  setOptions($("leg-filter"), legs, "Todos os trechos", legLabel);
}

function selectedFilters() {
  return {
    route: $("route-filter").value,
    airline: $("airline-filter").value,
    leg: $("leg-filter").value,
    stops: $("stops-filter").value,
    sort: $("sort-filter").value,
  };
}

function filteredOffers(offers) {
  const filters = selectedFilters();
  const result = array(offers).filter((offer) => {
    if (filters.route && routeLabel(offer.route) !== filters.route) return false;
    if (filters.airline && !airlines(offer).includes(filters.airline)) return false;
    if (filters.leg === "package" && !isPackageOffer(offer)) return false;
    if (filters.leg && filters.leg !== "package" && offer?.route?.leg !== filters.leg) return false;
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

  const filters = selectedFilters();
  const history = historyPoints(state.data?.history, filters.route, filters.leg);
  const lowest = history.filter((point) => finite(point.amount)).sort((left, right) => left.amount - right.amount)[0];
  $("history-price").textContent = lowest ? currency(lowest.amount, lowest.currency) : "—";
  $("history-price-detail").textContent = lowest ? `${routeLabel(lowest.route)} · menor preço diário` : "Histórico sem preço comparável.";

  const selected = selectedTotal(singleLegOffers(state.data?.offers));
  $("selected-total").textContent = selected?.incompatible ? "—" : selected ? currency(selected.amount, selected.currency) : "—";
  $("selected-total-detail").textContent = selected?.incompatible
    ? "Selecione trechos na mesma moeda."
    : selected
      ? `${selected.count} ${selected.count === 1 ? "trecho selecionado" : "trechos selecionados"}.`
      : "Selecione ofertas para somar.";
  $("clear-selection").disabled = !selected;
}

function renderOffer(offer) {
  const card = document.createElement("article");
  card.className = "offer-card";
  const selected = Boolean(offer?.id && state.selectedOfferIds.has(offer.id));
  if (selected) card.classList.add("offer-card-selected");
  const top = document.createElement("div");
  top.className = "offer-top";
  const heading = document.createElement("div");
  addText(heading, "div", routeLabel(offer.route), "route-name");
  addText(heading, "div", airlines(offer).join(", ") || "Companhia não informada", "muted");
  const topActions = document.createElement("div");
  topActions.className = "offer-top-actions";
  topActions.append(addText(document.createElement("div"), "div", money(offer), "offer-price"));
  const selectLabel = document.createElement("label");
  selectLabel.className = "offer-select";
  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.checked = selected;
  checkbox.disabled = !isComparable(offer) || !offer?.id || isPackageOffer(offer);
  checkbox.setAttribute("aria-label", `Selecionar ${routeLabel(offer.route)} por ${money(offer)}`);
  checkbox.addEventListener("change", () => {
    if (checkbox.checked) state.selectedOfferIds.add(offer.id);
    else state.selectedOfferIds.delete(offer.id);
    updateOffers();
  });
  selectLabel.append(checkbox, addText(document.createElement("span"), "span", "Somar"));
  topActions.append(selectLabel);
  top.append(heading, topActions);
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
  const more = $("show-more");
  clear(target);
  if (!offers.length) {
    addText(target, "p", "Nenhuma oferta atende aos filtros. Tente limpar a seleção.", "empty-state");
    more.hidden = true;
    return;
  }
  const visible = state.showAllOffers ? offers : offers.slice(0, MAX_VISIBLE_OFFERS);
  for (const offer of visible) target.append(renderOffer(offer));
  more.hidden = state.showAllOffers || offers.length <= MAX_VISIBLE_OFFERS;
  more.textContent = `Ver mais (${offers.length - MAX_VISIBLE_OFFERS})`;
}

function renderRoutes(data, offers = displayOffers(data.offers)) {
  const target = $("routes");
  clear(target);
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

function historyPoints(history, route, leg) {
  const points = [];
  for (const entry of array(history?.entries)) {
    for (const item of array(entry?.routes)) {
      if (route && routeLabel(item.route) !== route) continue;
      if (leg && item?.route?.leg !== leg) continue;
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
  const filters = selectedFilters();
  const points = historyPoints(history, filters.route, filters.leg).filter((point) => finite(point.amount));
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
  state.showAllOffers = false;
  state.selectedOfferIds.clear();
  renderSearch(data.search || {});
  $("schema-label").textContent = `JSON público · schema ${data.schema_version ?? "?"}`;
  $("last-updated").textContent = data.generated_at_utc ? `Última consulta: ${date(data.generated_at_utc)}` : "Última consulta: não informada";
  const stale = array(data.offers).some((offer) => offer.stale) || data.status === "stale_data";
  const alert = stale ? "Algumas ofertas são dados antigos porque uma ou mais rotas falharam." : (data.status === "failure" ? "Consulta teve falhas. Veja status por rota." : "");
  setStatus(data.status, alert);
  $("disclaimer").textContent = data.disclaimer || "Preço mantém interpretação da fonte. Taxas, bebê de colo, bagagem e inventário não são inferidos.";
  const offers = displayOffers(data.offers);
  renderFilters(offers, data.search);
  renderRoutes(data, offers);
  updateOffers();
}

function updateOffers() {
  if (!state.data) return;
  const offers = filteredOffers(displayOffers(state.data.offers));
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

for (const id of ["route-filter", "airline-filter", "leg-filter", "stops-filter", "sort-filter"]) {
  $(id).addEventListener("change", () => {
    state.showAllOffers = false;
    updateOffers();
  });
}
$("show-more").addEventListener("click", () => {
  state.showAllOffers = true;
  updateOffers();
});
$("clear-filters").addEventListener("click", () => {
  $("route-filter").value = "";
  $("airline-filter").value = "";
  $("leg-filter").value = "";
  $("stops-filter").value = "";
  $("sort-filter").value = "price";
  updateOffers();
});
$("clear-selection").addEventListener("click", () => {
  state.selectedOfferIds.clear();
  updateOffers();
});
$("reload").addEventListener("click", loadData);
loadData();
