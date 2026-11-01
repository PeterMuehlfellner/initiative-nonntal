[out:json][timeout:90];
(
  way["highway"](47.7895,13.0455,47.7945,13.0545);
  node["highway"="bus_stop"](47.7895,13.0455,47.7945,13.0545);
  node["public_transport"="platform"](47.7895,13.0455,47.7945,13.0545);
  node["highway"="crossing"](47.7895,13.0455,47.7945,13.0545);
  node["highway"="traffic_signals"](47.7895,13.0455,47.7945,13.0545);
  node["amenity"~"^(school|kindergarten|theatre|university)$"](47.7895,13.0455,47.7945,13.0545);
  way["amenity"~"^(school|kindergarten|theatre|university)$"](47.7895,13.0455,47.7945,13.0545);
  way["building"](47.7895,13.0455,47.7945,13.0545);
  way["natural"="water"](47.7895,13.0455,47.7945,13.0545);
  way["leisure"="park"](47.7895,13.0455,47.7945,13.0545);
  way["landuse"~"^(grass|forest|cemetery)$"](47.7895,13.0455,47.7945,13.0545);
);
out body geom;
