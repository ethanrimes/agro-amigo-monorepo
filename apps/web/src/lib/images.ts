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
  [/^(mini)?clavel\b/, "carnation-cut"],
  [/^crisantemo\b|^chrysanthemums?\b/, "chrysanthemum-cut"],
  [/^(lilies|lilium)\b/, "lily-cut"],
  [/^(tulips|tulipa)\b/, "tulip-cut"],
  [/^hortensia\b/, "hydrangea-cut"],
  [/^alstroemeria\b/, "alstroemeria-cut"],
  [/^gerbera\b/, "gerbera-cut"],
  [/^cala\b|^calla\b/, "calla-cut"],
  [/^limonium\b|^statice\b/, "statice-cut"],
  [/^peony\b|^paeonia\b/, "peony-cut"],
  [/^astilbe\b/, "astilbe-cut"],
  [/^liatris\b/, "liatris-cut"],
  [/rosa.*(red varieties|rojas?)/, "rose-red-cut"],
  [/\brosas?\b|^rose, garden hybrids\b/, "rose-colombia"],
  [/ganado (bovino|vacuno|gordo|flaco)|\bbovinos?\b/, "cattle-colombia"],
  [/arandano/, "blueberry"],
  [/jengibre/, "ginger"],
  [/camaron/, "shrimp"],
  [/atun (en lata|enlatado)/, "tuna-canned"],
  [/sardinas? en lata/, "sardines-canned"],
  [/capaz magdalena/, "capaz-fish"],
  [/pescado seco/, "dried-fish"],
  [/\bbagre\b/, "bagre"],
  [/\bbasa\b/, "basa"],
  [/boca\s*chico/, "bocachico"],
  [/cachama/, "cachama"],
  [/tilapia/, "tilapia"],
  [/trucha/, "trout"],
  // Mixed seafood, shellfish, squid and imitation crab are not whole fish.
  [/mariscos?|almejas?|calamar|palmitos de mar/, "produce-neutral"],
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
  [/^limon(?!ium)/, "lime"],
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
  [/^uva/, "grape"],
  [/melon/, "melon"],
  [/tangelo/, "tangelo"],
  [/zapote/, "zapote"],
  [/ajo/, "garlic"],
  [/alcachofa/, "artichoke"],
  [/apio/, "celery"],
  [/arveja seca/, "peas-dried"],
  [/arveja/, "peas"],
  [/berenjena/, "aubergine"],
  [/brocoli/, "broccoli"],
  [/ahuyama|zapallo/, "pumpkin"],
  [/ahuyamin|^calabaza$/, "squash-moschata"],
  [/calabacin/, "zucchini"],
  [/cebolla.*(junca|larga)/, "spring-onion"],
  [/cebollin chino/, "chinese-chives"],
  [/cebolla/, "onion"],
  [/cilantro/, "cilantro"],
  [/perejil/, "parsley"],
  [/colifl\s*or/, "cauliflower"],
  [/acelga/, "chard"],
  [/espinaca/, "spinach"],
  [/habichuela/, "beans-green"],
  [/haba verde/, "fava-green"],
  [/lechuga/, "lettuce"],
  [/chocolo|mazorca|maiz/, "corn"],
  [/pepino.*guiso|cidra/, "chayote"],
  [/pepino/, "cucumber"],
  [/pimenton.*verde/, "bell-pepper-green"],
  [/pimenton/, "bell-pepper"],
  [/aji (topito )?dulce/, "aji-dulce"],
  [/\baji\b/, "produce-neutral"],
  [/remolacha/, "beet"],
  [/rabano rojo/, "radish-red"],
  [/repollo/, "cabbage"],
  [/^coles$/, "cabbage"],
  [/zanahoria/, "carrot"],
  [/arracacha/, "arracacha"],
  [/yuca/, "cassava"],
  [/^name\b/, "yam"],
  [/ulluco/, "ullucus"],
  [/arroz/, "rice"],
  [/lenteja/, "lentils"],
  [/frijol/, "beans"],
  [/garbanzo/, "chickpeas"],
  [/avena/, "oats"],
  [/cuchuco de cebada/, "barley-groats"],
  [/^harinas$/, "produce-neutral"],
  [/harina/, "flour"],
  [/trigo/, "wheat"],
  [/mani/, "peanut"],
  [/panela/, "panela"],
  [/bocadillo veleno/, "bocadillo-colombiano"],
  [/^jugo de frutas$/, "fruit-juice-mix"],
  [/azucar/, "sugar"],
  [/aceite de palma|aceite vegetal palma/, "palm-oil-unbranded"],
  [/aceite (de )?girasol/, "sunflower-oil-unbranded"],
  [/aceite (de )?soya/, "soybean-oil-unbranded"],
  [/aceite/, "produce-neutral"],
  [/\bsal\b/, "salt"],
  [/pasta/, "pasta"],
  [/mayonesa/, "mayonnaise-unbranded"],
  [/mostaza/, "mustard-unbranded"],
  [/galletas dulces redondas con crema/, "cookies-sandwich"],
  [/galletas saladas/, "crackers-saltine"],
  [/chocolate/, "chocolate"],
  [/queso|cuajada/, "cheese"],
  [/leche/, "milk"],
  [/huevo/, "eggs"],
  [/mantequilla|margarina/, "butter"],
  [/pollo|pechuga|pernil con rabadilla|pernil sin rabadilla/, "chicken"],
  [/cerdo/, "pork"],
  [/carne (de )?res\b|carne bovina\b/, "beef"],
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
          : key === "sardines-canned"
            ? `Fotografía ilustrativa de sardinas en una lata abierta; el líquido y la presentación de ${name} pueden diferir.`
          : key === "crackers-saltine"
            ? `Fotografía ilustrativa de galletas saladas tipo cracker; no representa la marca ni la presentación comercial de ${name}.`
          : key === "cookies-sandwich"
            ? `Fotografía ilustrativa de galletas redondas con crema; el sabor, la marca y la presentación de ${name} pueden diferir.`
          : key === "tangelo"
            ? `Fotografía ilustrativa de un tangelo Minneola; la variedad y procedencia de ${name} pueden diferir.`
          : key === "sunflower-oil-unbranded"
            ? `Fotografía ilustrativa de aceite de girasol junto a una flor y semillas; no representa el refinado, origen ni empaque de ${name}.`
          : key === "soybean-oil-unbranded"
            ? `Fotografía ilustrativa de aceite de soya en un recipiente de laboratorio; no representa el refinado, origen ni empaque de ${name}.`
          : key === "aji-dulce"
            ? `Fotografía ilustrativa de un ají dulce; no acredita la variedad topito ni la procedencia de ${name}.`
          : key === "squash-moschata"
            ? `Fotografía ilustrativa de una calabaza Cucurbita moschata cortada; no acredita el cultivar ni la forma comercial de ${name}.`
          : key === "chinese-chives"
            ? `Fotografía ilustrativa de cebollino chino tipo ajo; la especie y presentación comercial de ${name} pueden diferir.`
          : key === "mayonnaise-unbranded"
            ? `Fotografía ilustrativa de mayonesa servida en un cuenco; no representa la marca ni el empaque doy pack de ${name}.`
          : key === "mustard-unbranded"
            ? `Fotografía ilustrativa de mostaza servida en un cuenco; no representa la marca ni el empaque doy pack de ${name}.`
          : key === "capaz-fish"
            ? `Fotografía ilustrativa de un ejemplar de Pimelodus grosskopfii; no verifica la especie, procedencia ni presentación comercial de ${name}.`
          : key === "barley-groats"
            ? `Fotografía ilustrativa de cebada quebrada sin cocinar; el molido y la presentación de ${name} pueden diferir.`
          : key === "bocadillo-colombiano"
            ? `Fotografía ilustrativa de bocadillo colombiano envuelto en hoja; no acredita el origen veleño ni el productor de ${name}.`
          : key === "fruit-juice-mix"
            ? `Fotografía ilustrativa de una mezcla de jugos de frutas servida en vaso; el sabor y la presentación comercial de ${name} pueden diferir.`
          : key === "cabbage" && n === "coles"
            ? `Fotografía ilustrativa de repollo como ejemplo de las coles; no identifica la variedad comercial de ${name}.`
          : key === "fava-green"
            ? `Fotografía ilustrativa de habas verdes en vaina; la presentación de ${name} puede diferir.`
          : key === "parsley"
            ? `Fotografía ilustrativa de una planta de perejil; la presentación comercial de ${name} puede diferir.`
          : ["bagre", "basa", "bocachico", "cachama", "tilapia", "trout", "dried-fish"].includes(key)
            ? `Fotografía ilustrativa para ${name}. ${imageLibrary[key].description}`
          : key === "palm-oil-unbranded"
            ? `Fotografía ilustrativa de aceite de palma sin marca; la textura y presentación de ${name} pueden diferir.`
          : key === "oil-palm-fruit"
            ? `Fotografía ilustrativa del fruto de palma de aceite; no representa el producto comercial ${name}.`
          : key === "rose-red-cut"
            ? `Fotografía ilustrativa de rosas rojas cortadas; no acredita la variedad, longitud ni origen de ${name}.`
          : ["carnation-cut", "chrysanthemum-cut", "lily-cut", "tulip-cut", "hydrangea-cut", "alstroemeria-cut", "gerbera-cut", "calla-cut", "statice-cut", "peony-cut", "astilbe-cut", "liatris-cut"].includes(key)
            ? `Fotografía ilustrativa de la familia floral de ${name}; el color, la variedad, la longitud y la presentación comercial pueden diferir.`
          : key === "rose-colombia"
            ? `Fotografía ilustrativa de una rosa rosada de jardín; el color y la presentación comercial de ${name} pueden diferir.`
          : key === "fish"
            ? `Fotografía ilustrativa de pescado entero en un mercado; no identifica la especie, el corte ni la presentación comercial de ${name}.`
          : key === "beef"
            ? `Fotografía ilustrativa de carne bovina; no identifica el corte, origen ni presentación comercial de ${name}.`
          : key === "salt"
            ? `Fotografía ilustrativa de sal marina gruesa; la presentación de ${name} puede diferir.`
          : key === "bell-pepper-green"
            ? `Fotografía ilustrativa de pimentones verdes; la variedad y procedencia de ${name} pueden diferir.`
          : ["cacao-pods", "sugarcane-colombia", "rose-colombia", "cattle-colombia"].includes(key)
            ? `Fotografía ilustrativa del cultivo o especie de ${name}; la presentación comercial puede diferir.`
          : `${visual} de ${name}; la variedad puede diferir.`;
  return { src, alt, key };
}
