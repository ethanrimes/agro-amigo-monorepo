import library from "./image-library.json";
import { fold } from "./planning-math";
type Photo = {
  src: string;
  title: string;
  source: string;
  author: string;
  license: string;
  licenseUrl: string;
  description: string;
  illustrative: boolean;
};
export const imageLibrary = library as Record<string, Photo>;
const families: [RegExp, string][] = [
  [/cafe.*(instantaneo|molido|tostado)/, "coffee-roasted"],
  [/aguacate/, "avocado"],
  [/tomate de arbol/, "tamarillo"],
  [/tomate/, "tomato"],
  [/\bpapa\b/, "potato"],
  [/platano/, "plantain"],
  [/banano/, "banana"],
  [/arandano/, "blueberry"],
  [/badea/, "badea"],
  [/borojo/, "borojo"],
  [/breva|higo/, "fig"],
  [/ciruela/, "plum"],
  [/coco/, "coconut"],
  [/curuba/, "curuba"],
  [/durazno/, "peach"],
  [/feijoa/, "feijoa"],
  [/fresa/, "strawberry"],
  [/granadilla/, "granadilla"],
  [/guanabana/, "soursop"],
  [/guayaba/, "guava"],
  [/gulupa|maracuya/, "passionfruit"],
  [/kiwi/, "kiwi"],
  [/limon/, "lime"],
  [/lulo/, "lulo"],
  [/mandarina/, "mandarin"],
  [/mango/, "mango"],
  [/manzana/, "apple"],
  [/mora/, "blackberry"],
  [/naranja/, "orange"],
  [/papaya/, "papaya"],
  [/patilla/, "watermelon"],
  [/pera/, "pear"],
  [/pina/, "pineapple"],
  [/pitahaya/, "pitaya"],
  [/uchuva/, "uchuva"],
  [/uva/, "grape"],
  [/melon/, "melon"],
  [/zapote/, "zapote"],
  [/ajo/, "garlic"],
  [/alcachofa/, "artichoke"],
  [/apio/, "celery"],
  [/arveja/, "peas"],
  [/berenjena/, "aubergine"],
  [/brocoli/, "broccoli"],
  [/ahuyama|zapallo/, "pumpkin"],
  [/calabacin/, "zucchini"],
  [/cebolla.*(junca|larga)/, "spring-onion"],
  [/cebolla/, "onion"],
  [/cilantro/, "cilantro"],
  [/coliflor/, "cauliflower"],
  [/espinaca|acelga/, "spinach"],
  [/habichuela/, "beans-green"],
  [/lechuga/, "lettuce"],
  [/chocolo|mazorca|maiz/, "corn"],
  [/pepino.*guiso|cidra/, "chayote"],
  [/pepino/, "cucumber"],
  [/pimenton|aji/, "bell-pepper"],
  [/remolacha/, "beet"],
  [/repollo/, "cabbage"],
  [/zanahoria/, "carrot"],
  [/arracacha/, "arracacha"],
  [/yuca/, "cassava"],
  [/name/, "yam"],
  [/ulluco/, "ullucus"],
  [/arroz/, "rice"],
  [/lenteja/, "lentils"],
  [/frijol/, "beans"],
  [/garbanzo/, "chickpeas"],
  [/avena/, "oats"],
  [/trigo/, "wheat"],
  [/mani/, "peanut"],
  [/panela/, "panela"],
  [/azucar/, "sugar"],
  [/harina/, "flour"],
  [/aceite/, "oil"],
  [/sal /, "salt"],
  [/pasta/, "pasta"],
  [/chocolate/, "chocolate"],
  [/queso|cuajada/, "cheese"],
  [/leche/, "milk"],
  [/huevo/, "eggs"],
  [/mantequilla|margarina/, "butter"],
  [/pollo|pechuga|pernil con rabadilla|pernil sin rabadilla/, "chicken"],
  [/cerdo/, "pork"],
  [/carne de res/, "beef"],
  [/camaron/, "shrimp"],
  [/cafe/, "coffee"],
];
const existing = new Set([
  "coffee",
  "avocado",
  "tomato",
  "potato",
  "banana",
  "plantain",
  "produce",
  "farm",
]);
export function photoFor(
  name: string,
  category = "",
  kind: "product" | "input" | "market" = "product",
): { src: string; alt: string; key: string } {
  const n = fold(name);
  let key = "produce";
  if (kind === "product")
    key =
      families.find(([re]) => re.test(n))?.[1] ||
      (category === "Pescados"
        ? "fish"
        : category === "Carnes"
          ? "beef"
          : "produce");
  if (kind === "input") {
    const c = fold(category);
    // Material photos only describe fertilizers/amendments. Equipment, animals,
    // services and medicines must never inherit the generic DAP photograph.
    const material = /fertilizante|enmienda|abono/.test(c);
    key = material && /\bcal\b|caliza|carbonato|dolomita/.test(n)
      ? "limestone"
      : material && /organico|abonaza|compost/.test(n)
        ? "compost"
        : material && /azufre/.test(n)
          ? "sulphur"
          : material && /potasio/.test(n)
            ? "potassium"
            : /bioinsumos/i.test(category)
              ? "bioinput"
              : /fertilizante|fungicida|herbicida|insecticida|acaricida|coadyuvante|medicamento|antibiotico|antiparasitario/.test(c) && /litro|cubicos/.test(c)
                ? "liquid-input"
                : material
                  ? "fertilizer"
                  : "input-neutral";
  }
  if (kind === "market")
    key = n.includes("corabastos")
      ? "corabastos"
      : n.includes("paloquemao")
        ? "paloquemao"
        : n.includes("minorista")
          ? "minorista"
          : n.includes("bazurto")
            ? "bazurto"
            : n.includes("alameda")
              ? "alameda"
              : n.includes("almacafe")
                ? "market-coffee"
                : /molino|arrocera/.test(n)
                  ? "market-rice"
                  : "market";
  const src =
    imageLibrary[key]?.src ||
    (existing.has(key)
      ? `/images/${key}.jpg`
      : imageLibrary[
          kind === "input"
            ? "input-neutral"
            : kind === "market"
              ? "market"
              : "produce"
        ]?.src || "/images/produce.jpg");
  const visual = src.endsWith(".svg") ? "Ilustración" : "Foto ilustrativa";
  const alt =
    kind === "input"
      ? key === "input-neutral"
        ? `Ilustración general de insumos y servicios agrícolas; no representa ${name}.`
        : `${visual} del tipo de insumo; no corresponde al empaque comercial de ${name}.`
      : kind === "market"
        ? key === "market" || key.startsWith("market-")
          ? "Imagen ilustrativa de una plaza o centro de acopio."
          : `Fotografía de referencia: ${name}`
        : `${visual} de ${name}; la variedad puede diferir.`;
  return { src, alt, key };
}
