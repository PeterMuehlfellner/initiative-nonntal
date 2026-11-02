[out:json][timeout:90];
(
  nwr["amenity"~"^(school|kindergarten|childcare|college|university|hospital|theatre|social_facility|nursing_home|retirement_home|rehearsal_studio|arts_centre|music_school)$"](around:900,47.7920,13.0503);
  nwr["leisure"="playground"](around:900,47.7920,13.0503);
  nwr["social_facility"](around:900,47.7920,13.0503);
);
out center tags;
