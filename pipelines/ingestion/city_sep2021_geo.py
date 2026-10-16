"""PRIVATE source-bound geo sidecar; never rewrites printed quote market labels."""
from .city_sep2021_heading import EXPECTED_MARKETS
from .worker import slug

# Ten source-name+municipality matches were independently checked against the
# existing market directory. Villavicencio is a *separate* printed identity;
# CAV facility equivalence has not been established.
GEO = {
 'f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93': ('11001','sipsa-bogota-d-c-corabastos','Bogotá, D.C.'),
 'f74ba57880a0a199d6926b8fb5652b652926d7d6ec7bfd17efea320186de1b2c': ('08001','sipsa-barranquilla-granabastos','Atlántico'),
 '16381c4b870066c7f3f4aab8c0d732dc36187d3b088c68bb308a46ec6c33b463': ('13001','sipsa-cartagena-bazurto','Bolívar'),
 'd0403c415af395c5bca852a4dd6977dfb1d5a784e040d579d58d0d9f97efdbee': ('23001','sipsa-monteria-mercado-del-sur','Córdoba'),
 '36058d3e2ab35b83737c3379870dfc94cfc8f93798f6873101beb296f2bd68ad': ('05001','sipsa-medellin-central-mayorista-de-antioquia','Antioquia'),
 'eaaafa06421b7ffba4828df57827e90987d9e889bbd854d5174b88831a32148f': ('66001','sipsa-pereira-mercasa','Risaralda'),
 '301dff168ebe1cc357fd2bf0cc84409b28410e418ff57a43250c05b78a846e66': ('19001','sipsa-popayan-plaza-de-mercado-del-barrio-bolivar','Cauca'),
 'cc58e5ce38fa751138de088436ece59fb35610fc14eca39d1811f76d2009bd78': ('47001','sipsa-santa-marta-magdalena','Magdalena'),
 '32c73fee19652051a882222b51178105fd36e65098c9004992bfb971ead116fc': ('70001','sipsa-sincelejo-nuevo-mercado','Sucre'),
 '479bb6418ba84694e41bdf3b6249761127dd88fa1227b5e2dd3e3975430d5aa6': ('50001','dane-city-villavicencio-central-de-abastos-de-villavicencio','Meta'),
 '80009b21f92c47bac30d7a8d181605682fa3404c43a96610d93305b4cfbf1058': ('20001','sipsa-valledupar-mercabastos','Cesar'),
}
CITY = {
 '11001':'Bogotá, D.C.', '08001':'Barranquilla', '13001':'Cartagena De Indias',
 '23001':'Montería', '05001':'Medellín', '66001':'Pereira', '19001':'Popayán',
 '47001':'Santa Marta', '70001':'Sincelejo', '50001':'Villavicencio',
 '20001':'Valledupar',
}

def source_geo(child_sha, literal_market):
    if child_sha not in EXPECTED_MARKETS or literal_market != EXPECTED_MARKETS[child_sha]:
        raise ValueError('Unverified Sep 2021 printed city/market identity')
    municipality_id, geo_match_id, region = GEO[child_sha]
    # The price keeps its own exact printed identity. The pre-existing match
    # supplies municipality/region only; it is not a quote-ID alias.
    # The ordinary Bogotá slug is already owned by the distinct historical
    # literal "Bogotá, Corabastos". Valledupar has an existing market row
    # with the exact same printed name and municipality; reuse it to avoid a
    # duplicate-name market join. Neither case rewrites the raw source label.
    literal_market_id = (
        'dane-city-bogota-corabastos-f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93'
        if child_sha == 'f5d39758d2921991b120381bafbfa2f3dd3cdd07cbbdfc8611f60d51c3a5dd93'
        else 'sipsa-valledupar-mercabastos'
        if child_sha == '80009b21f92c47bac30d7a8d181605682fa3404c43a96610d93305b4cfbf1058'
        else 'dane-city-' + slug(literal_market)
    )
    return {'document_id':child_sha, 'literal_market':literal_market,
            'municipality_id':municipality_id,'city':CITY[municipality_id],
            'literal_market_id':literal_market_id,
            'geo_match_id':None if municipality_id=='50001' else geo_match_id,
            'region':region,
            'facility_equivalence_unverified':municipality_id=='50001'}

assert set(GEO)==set(EXPECTED_MARKETS)
assert GEO['479bb6418ba84694e41bdf3b6249761127dd88fa1227b5e2dd3e3975430d5aa6'][1] != 'sipsa-villavicencio-cav'
