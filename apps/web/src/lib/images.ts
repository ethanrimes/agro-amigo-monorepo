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
  if (kind === "input")
    key = /cal |caliza|carbonato|dolomita/.test(n)
      ? "limestone"
      : /organico|abonaza|compost/.test(n)
        ? "compost"
        : /azufre/.test(n)
          ? "sulphur"
          : /potasio/.test(n)
            ? "potassium"
            : /bioinsumos/i.test(category)
              ? "bioinput"
              : /litro|cubicos/.test(fold(category))
                ? "liquid-input"
                : "fertilizer";
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
            ? "fertilizer"
            : kind === "market"
              ? "market"
              : "produce"
        ]?.src || "/images/produce.jpg");
  const visual = src.endsWith(".svg") ? "Ilustración" : "Foto ilustrativa";
  const alt =
    kind === "input"
      ? `${visual} del tipo de insumo; no corresponde al empaque comercial de ${name}.`
      : kind === "market"
        ? key === "market" || key.startsWith("market-")
          ? "Imagen ilustrativa de una plaza o centro de acopio."
          : `Fotografía de referencia: ${name}`
        : `${visual} de ${name}; la variedad puede diferir.`;
  return { src, alt, key };
}
