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
  modifications?: string;
};
export const imageLibrary = library as Record<string, Photo>;
const families: [RegExp, string][] = [
  [/cafe.*tostado/, "coffee-roasted"],
  [/cafe.*(instantaneo|soluble)/, "coffee-instant"],
  [/cafe.*molido/, "coffee-ground"],
  [/cafe.*pergamino/, "coffee-parchment"],
  [/cafe.*(almendra sana|excelso)/, "coffee-green-beans"],
  [/aguacate/, "avocado"],
  [/tomate de arbol/, "tamarillo"],
  [/tomate/, "tomato"],
  [/\bpapas?\b/, "potato"],
  [/platano/, "plantain"],
  [/banano/, "banana"],
  [/chocolate/, "chocolate"],
  [/cacao.*polvo/, "cocoa-powder"],
  [/cacao.*(manteca|licor)/, "produce-neutral"],
  [/cacao/, "cacao-pods"],
  [/can[a] de azucar/, "sugarcane-colombia"],
  [/^palma$|palma (de aceite|africana)|fruto de palma|palmiste/, "oil-palm-fruit"],
  [/rosa.*(red varieties|rojas?)/, "rose-red-cut"],
  [/\brosas?\b/, "rose-colombia"],
  [/ganado (bovino|vacuno|gordo|flaco)|\bbovinos?\b/, "cattle-colombia"],
  [/arandano/, "blueberry"],
  [/jengibre/, "ginger"],
  [/camaron/, "shrimp"],
  [/atun (en lata|enlatado)/, "tuna-canned"],
  [/pescado seco/, "dried-fish"],
  [/\bbagre\b/, "bagre"],
  [/\bbasa\b/, "basa"],
  [/bocachico/, "bocachico"],
  [/cachama/, "cachama"],
  [/tilapia/, "tilapia"],
  [/trucha/, "trout"],
  [/mariscos? otros/, "produce-neutral"],
  [/frijol verde/, "beans-green"],
  [/res en pie|ganado en pie/, "cattle-colombia"],
  // Live animals should not inherit photographs of butchered meat.
  [/cerdo en pie|pollo en pie|gallina en pie/, "produce-neutral"],
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
  [/arveja seca/, "peas-dried"],
  [/arveja/, "peas"],
  [/berenjena/, "aubergine"],
  [/brocoli/, "broccoli"],
  [/ahuyama|zapallo/, "pumpkin"],
  [/calabacin/, "zucchini"],
  [/cebolla.*(junca|larga)/, "spring-onion"],
  [/cebolla/, "onion"],
  [/cilantro/, "cilantro"],
  [/coliflor/, "cauliflower"],
  [/acelga/, "chard"],
  [/espinaca/, "spinach"],
  [/habichuela/, "beans-green"],
  [/lechuga/, "lettuce"],
  [/chocolo|mazorca|maiz/, "corn"],
  [/pepino.*guiso|cidra/, "chayote"],
  [/pepino/, "cucumber"],
  [/pimenton.*verde/, "bell-pepper-green"],
  [/pimenton/, "bell-pepper"],
  [/\baji\b/, "produce-neutral"],
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
  [/^harinas$/, "produce-neutral"],
  [/harina/, "flour"],
  [/trigo/, "wheat"],
  [/mani/, "peanut"],
  [/panela/, "panela"],
  [/azucar/, "sugar"],
  [/aceite de palma/, "palm-oil-unbranded"],
  [/aceite/, "produce-neutral"],
  [/\bsal\b/, "salt"],
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
  [/cafe/, "produce-neutral"],
];
export function photoFor(
  name: string,
  category = "",
  kind: "product" | "input" | "market" = "product",
): { src: string; alt: string; key: string } {
  const n = fold(name);
  let key = "produce-neutral";
  if (kind === "product")
    key =
      families.find(([re]) => re.test(n))?.[1] ||
      (category === "Pescados"
        ? "fish"
        : "produce-neutral");
  if (kind === "input") {
    const c = fold(category);
    // Material photos only describe fertilizers/amendments. Equipment, animals,
    // services and medicines must never inherit the generic DAP photograph.
    const material = /fertilizante|enmienda|abono/.test(c);
    const plantingMaterial = /plantula|planta viva|esqueje|material vegetal|material de propagacion/.test(n) ||
      (!/semill/.test(c) && /material vegetal|material de propagacion/.test(c));
    key = plantingMaterial && !/semill/.test(n)
      ? "seedlings-general"
      : /semill/.test(c) || /semill/.test(n)
      ? "seeds-general"
      : material && /\bcal\b|caliza|carbonato|dolomita/.test(n)
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
      : /(medellin.*minorista|plaza minorista jose maria villa)/.test(n)
          ? "minorista"
          : n.includes("bazurto")
            ? "bazurto"
            : "market-neutral";
  // Prefer subject-specific credited photos. Keep an illustration for products
  // that cannot be matched without implying a particular crop or commercial SKU.
  if (!imageLibrary[key]) key = kind === "input" ? "input-neutral" : kind === "market" ? "market-neutral" : "produce-neutral";
  const src = imageLibrary[key].src;
  const visual = src.endsWith(".svg") ? "Ilustración" : "Foto ilustrativa";
  const alt =
    kind === "input"
      ? key === "input-neutral"
        ? `Ilustración general de insumos y servicios agrícolas; no representa ${name}.`
        : key === "seeds-general"
          ? `Fotografía ilustrativa de una biblioteca de semillas; no representa el producto comercial ${name}.`
        : key === "seedlings-general"
          ? `Fotografía ilustrativa de plántulas; no representa la especie ni el producto comercial ${name}.`
        : `${visual} del tipo de insumo; no corresponde al empaque comercial de ${name}.`
      : kind === "market"
        ? key === "market-neutral"
          ? `Ilustración general de una plaza de mercado; no representa ${name}.`
          : `Fotografía de referencia: ${name}`
        : key === "produce-neutral"
          ? `Ilustración general de productos agrícolas; no representa ${name}.`
          : key === "coffee-parchment"
            ? `Fotografía ilustrativa de café pergamino; la presentación de ${name} puede diferir.`
          : key === "coffee-green-beans"
            ? `Fotografía ilustrativa de granos de café sin tostar; no acredita el origen ni grado comercial de ${name}.`
          : key === "coffee-ground"
            ? `Fotografía ilustrativa de café molido sin marca; no acredita el origen ni la presentación comercial de ${name}.`
          : key === "coffee-instant"
            ? `Fotografía ilustrativa de un gránulo de café instantáneo; la presentación de ${name} puede diferir.`
          : key === "cocoa-powder"
            ? `Fotografía ilustrativa de cacao en polvo; no acredita el origen ni la presentación comercial de ${name}.`
          : key === "peas-dried"
            ? `Fotografía ilustrativa de arvejas secas enteras; el color y origen de ${name} pueden diferir.`
          : key === "tuna-canned"
            ? `Fotografía ilustrativa de atún en una lata abierta; no representa la marca ni la presentación comercial de ${name}.`
          : ["bagre", "basa", "bocachico", "cachama", "tilapia", "trout", "dried-fish"].includes(key)
            ? `Fotografía ilustrativa para ${name}. ${imageLibrary[key].description}`
          : key === "palm-oil-unbranded"
            ? `Fotografía ilustrativa de aceite de palma sin marca; la textura y presentación de ${name} pueden diferir.`
          : key === "oil-palm-fruit"
            ? `Fotografía ilustrativa del fruto de palma de aceite; no representa el producto comercial ${name}.`
          : key === "rose-red-cut"
            ? `Fotografía ilustrativa de rosas rojas cortadas; no acredita la variedad, longitud ni origen de ${name}.`
          : key === "rose-colombia"
            ? `Fotografía ilustrativa de una rosa rosada de jardín; el color y la presentación comercial de ${name} pueden diferir.`
          : key === "salt"
            ? `Fotografía ilustrativa de sal marina gruesa; la presentación de ${name} puede diferir.`
          : key === "bell-pepper-green"
            ? `Fotografía ilustrativa de pimentones verdes; la variedad y procedencia de ${name} pueden diferir.`
          : ["cacao-pods", "sugarcane-colombia", "rose-colombia", "cattle-colombia"].includes(key)
            ? `Fotografía ilustrativa del cultivo o especie de ${name}; la presentación comercial puede diferir.`
          : `${visual} de ${name}; la variedad puede diferir.`;
  return { src, alt, key };
}
