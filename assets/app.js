/* Initiative Erzabt-Klotz-Straße, Seitenlogik.
   Kein Framework, keine Netzwerkaufrufe, keine Datenerhebung.
   Grafiken und Daten kommen aus karten.js (erzeugt von daten/build.py). */

(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);

  /* ------------------------------------------------ Hell / Dunkel ----- */
  const schalter = $("#thema");
  const gespeichert = (() => {
    try { return localStorage.getItem("thema"); } catch { return null; }
  })();
  if (gespeichert) document.documentElement.dataset.theme = gespeichert;

  if (schalter) {
    schalter.addEventListener("click", () => {
      const wurzel = document.documentElement;
      const dunkelJetzt = wurzel.dataset.theme
        ? wurzel.dataset.theme === "dark"
        : matchMedia("(prefers-color-scheme: dark)").matches;
      const neu = dunkelJetzt ? "light" : "dark";
      wurzel.dataset.theme = neu;
      try { localStorage.setItem("thema", neu); } catch { /* egal */ }
      schalter.setAttribute(
        "aria-label",
        neu === "dark" ? "Zu hellem Erscheinungsbild wechseln"
                       : "Zu dunklem Erscheinungsbild wechseln"
      );
    });
  }

  /* ------------------------------------------------------ Grafiken ---- */
  const grafiken = [
    ["#karte-geo", "geo"],
    ["#karte-quer", "quer"],
    ["#karte-halt", "halt"],
  ];
  for (const [sel, schluessel] of grafiken) {
    const ziel = $(sel);
    if (ziel && window.KARTEN && window.KARTEN[schluessel]) {
      ziel.innerHTML = window.KARTEN[schluessel];
    }
  }

  /* -------------------------------------- Legende und Kartenmarken ---- */
  const legende = $("#legende");
  if (legende && Array.isArray(window.MARKEN)) {
    // In der kompakten Fassung steht nur die Kurzbezeichnung; die ausführliche
    // Erklärung bleibt als Tooltip und für Screenreader erhalten.
    const kompakt = legende.classList.contains("legende--kompakt");
    legende.innerHTML = window.MARKEN
      .map(
        (m) => `<li data-nr="${m.nr}">
          <button type="button" title="${m.lang.replace(/"/g, "&quot;")}">
            <span class="legende__nr f-${m.farbe}">${m.nr}</span>
            <span class="legende__text">${m.kurz}${
              kompakt
                ? `<span class="sr-only">. ${m.lang}</span>`
                : `<span class="legende__lang">${m.lang}</span>`
            }</span>
          </button>
        </li>`
      )
      .join("");

    const marken = Array.from(document.querySelectorAll(".marke"));
    const punkte = Array.from(legende.querySelectorAll("li"));

    const hervorheben = (nr, an) => {
      for (const el of marken) el.classList.toggle("an", an && el.dataset.nr === String(nr));
      for (const li of punkte) li.classList.toggle("an", an && li.dataset.nr === String(nr));
    };

    for (const li of punkte) {
      const nr = li.dataset.nr;
      const knopf = li.querySelector("button");
      li.addEventListener("mouseenter", () => hervorheben(nr, true));
      li.addEventListener("mouseleave", () => hervorheben(nr, false));
      knopf.addEventListener("focus", () => hervorheben(nr, true));
      knopf.addEventListener("blur", () => hervorheben(nr, false));
      // Auf Touchgeräten: antippen hebt hervor und scrollt die Karte heran
      knopf.addEventListener("click", () => {
        hervorheben(nr, true);
        const karte = $("#karte-geo");
        if (karte && window.matchMedia("(max-width: 949px)").matches) {
          karte.scrollIntoView({ block: "center", behavior: "smooth" });
        }
      });
    }

    for (const el of marken) {
      const nr = el.dataset.nr;
      el.addEventListener("mouseenter", () => hervorheben(nr, true));
      el.addEventListener("mouseleave", () => hervorheben(nr, false));
      el.addEventListener("focus", () => hervorheben(nr, true));
      el.addEventListener("blur", () => hervorheben(nr, false));
    }
  }

  /* ----------------------------------------- Tabelle der Einrichtungen */
  const zieleKoerper = document.querySelector("#ziele tbody");
  if (zieleKoerper && Array.isArray(window.ZIELE)) {
    zieleKoerper.innerHTML = window.ZIELE
      .map(
        (z) =>
          `<tr><td>${z.name}</td><td>${z.art}</td>` +
          `<td class="num">${z.m} m</td></tr>`
      )
      .join("");
  }

  /* ------------------------------------------------- Brief an die Stadt */
  // MA 1/07 ist die zuständige Behörde, Stadträtin Schiester führt das
  // Ressort Stadtplanung, Verkehr und Klimaschutz, der Bürgermeister in Kopie.
  const EMPFAENGER = [
    "post@stadt-salzburg.at",
    "stadtraetin.schiester@stadt-salzburg.at",
    "bgm@stadt-salzburg.at",
  ];
  const BETREFF =
    "Erzabt-Klotz-Straße: Ersuchen um eine Querungsmöglichkeit und Tempo 30";

  const ENTWURF = `Sehr geehrte Damen und Herren des Verkehrs- und Straßenrechtsamtes,
sehr geehrte Frau Stadträtin Schiester,
sehr geehrter Herr Bürgermeister Auinger,

als Anrainerin bzw. Anrainer im Nonntal ersuche ich Sie, die Querungssituation in der Erzabt-Klotz-Straße zwischen der Kreuzung Petersbrunnstraße/Akademiestraße und der Nonntaler Hauptstraße zu prüfen.

Auf diesem Abschnitt gibt es genau eine gesicherte Stelle, an der die Fahrbahn überquert werden kann: die Bedarfsampel an der Kreuzung Petersbrunnstraße/Akademiestraße. Südwestlich davon folgen 280 Meter ohne weitere gesicherte Querung, bis die Straße nach der Kurve in die Nonntaler Hauptstraße übergeht. Die beiden Bushaltestellen der Linien 5, 9 und 25 liegen einander in dieser Strecke gegenüber; bis zur Ampel sind es von dort 123 Meter. Ein Seitenwechsel ist für viele unvermeidlich, und gequert wird daher an den Haltestellen, über die gesamte Fahrbahn.

[Hier bitte einen eigenen Satz einfügen: Wie erleben Sie die Stelle? Queren Sie dort selbst, mit Kindern, zu welcher Tageszeit?]

Ich ersuche um Prüfung folgender Maßnahmen:

1. Eine Mittelinsel auf Höhe der Haltestellen. Sie ermöglicht das Queren in zwei Schritten und unterbricht zugleich die durchgehende Fahrbahnfläche, was erfahrungsgemäß geschwindigkeitsdämpfend wirkt. Ein Schutzweg oder eine Bedarfsampel wären gleichwertige Lösungen; es geht um die gesicherte Querung, nicht um eine bestimmte Bauform.

2. Tempo 30 auf diesem Abschnitt. Im Umkreis von 600 Metern liegen sieben Schulen und zwei Kindergärten; die nächste Einrichtung für Kinder ist 124 Meter entfernt. § 43 Abs. 4a StVO in der Fassung seit 1. Juli 2024 sieht für solche Bereiche ausdrücklich vor, dass dafür keine Unfallstatistik und keine Verkehrszählung vorzulegen ist.

3. Eine raschere Grünschaltung der Bedarfsampeln an der Kreuzung Petersbrunnstraße/Akademiestraße, soweit das mit der Signalsteuerung der Obus-Linie vereinbar ist.

Mir ist bewusst, dass eine bauliche Maßnahme die Zustimmung des Landes Salzburg als Straßenerhalter und, wegen der Obus-Anlagen, der Salzburg AG erfordert. Ich ersuche daher auch um Auskunft, welche Stelle das Anliegen weiterverfolgt.

Über eine kurze Rückmeldung zum weiteren Vorgehen würde ich mich freuen.

Mit freundlichen Grüßen


[Ihr Name]
[Ihre Adresse]`;

  const feld = $("#entwurf");
  const mailto = $("#mailto");
  if (feld) feld.value = ENTWURF;

  const linkBauen = () => {
    if (!mailto) return;
    const text = feld ? feld.value : ENTWURF;
    mailto.href =
      "mailto:" +
      encodeURIComponent(EMPFAENGER[0]) +
      "?cc=" +
      encodeURIComponent(EMPFAENGER.slice(1).join(",")) +
      "&subject=" +
      encodeURIComponent(BETREFF) +
      "&body=" +
      encodeURIComponent(text);
  };
  linkBauen();
  if (feld) feld.addEventListener("input", linkBauen);

  const kopieren = $("#kopieren");
  if (kopieren && feld) {
    kopieren.addEventListener("click", async () => {
      const urspruenglich = kopieren.textContent;
      try {
        await navigator.clipboard.writeText(feld.value);
        kopieren.textContent = "Kopiert ✓";
      } catch {
        feld.select();
        // Auf Mobilgeräten gibt es kein Strg+C
        const mobil = window.matchMedia("(pointer: coarse)").matches;
        kopieren.textContent = mobil
          ? "Markiert, jetzt „Kopieren“ wählen"
          : "Bitte mit Strg+C kopieren";
      }
      setTimeout(() => { kopieren.textContent = urspruenglich; }, 2600);
    });
  }
})();
