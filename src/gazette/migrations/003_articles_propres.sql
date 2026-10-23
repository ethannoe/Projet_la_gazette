-- Les articles qui passent toutes les règles d'exclusion : la matière de la gazette.
-- Traçabilité : item_id est le nom du fichier brut, articles_bruts/<source_id>/<item_id>.json
CREATE TABLE articles_propres (
    item_id      text PRIMARY KEY,
    source_id    text NOT NULL REFERENCES sources (id),
    lien         text NOT NULL,
    titre        text NOT NULL,
    extrait      text NOT NULL,                 -- 300 caractères au plus
    publie_le    timestamptz NOT NULL,
    recupere_le  timestamptz NOT NULL,
    rubrique     text,
    titre_cle    text NOT NULL,                 -- titre normalisé, pour les doublons
    passage      timestamptz NOT NULL,          -- le passage de nettoyage qui l'a gardé
    UNIQUE (source_id, lien)
);

CREATE INDEX articles_propres_publie_le ON articles_propres (publie_le DESC);
CREATE INDEX articles_propres_passage ON articles_propres (passage);

-- Les items écartés, avec la règle qui les a écartés et ce qui l'a déclenchée.
CREATE TABLE rejets (
    item_id    text PRIMARY KEY,
    source_id  text NOT NULL REFERENCES sources (id),
    regle      text NOT NULL,                   -- ex. R02_horoscope
    detail     text,                            -- motif trouvé, article gardé à la place…
    titre      text NOT NULL,
    lien       text NOT NULL,
    passage    timestamptz NOT NULL
);

CREATE INDEX rejets_passage ON rejets (passage);
CREATE INDEX rejets_regle ON rejets (regle);
