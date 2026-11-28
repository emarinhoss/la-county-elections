## SVC rehearsal (city from precinct geometry)
- contest blocks parsed: **409** (0 with errors, 275 with notes)
- the county labels this file: {'FINAL OFFICIAL V2': 409}
- unique precincts: 2,218; assigned by: {'geo': 1831, 'geo_unincorporated': 383, 'location': 4}
- precincts under 90% inside their city (straddle a city line): 8
- contest evidence vs geometry: 1296/1386 agree (0.9351); top disagreements (geometry, contest, n): [('(unincorporated)', 'Los Angeles', 60), ('Gardena', 'Los Angeles', 9), ('Bell', 'Los Angeles', 6), ('(unincorporated)', 'Whittier', 4), ('Lomita', 'Los Angeles', 3), ('San Fernando', 'Los Angeles', 3)]
- registration in each city's own contests vs the geometric city: 47 of 49 comparable cities within 1%, 49 within 5%; largest differences: [('Irwindale', -1.7), ('Whittier', -1.19), ('El Monte', -0.28), ('Hawthorne', -0.2)]; not comparable (only council-district contests): ['Arcadia', 'Azusa', 'Bellflower', 'Claremont', 'Downey', 'Duarte', 'Glendora', 'La Verne', 'Pomona', 'Santa Clarita']
- place-name rule vs geometry: 1830/1837 correct (0.9962)
- boundary cities with at least one precinct: 88 of 88
- countywide blocks: 50; vote totals equal the printed GRAND TOTAL in all: **True**
