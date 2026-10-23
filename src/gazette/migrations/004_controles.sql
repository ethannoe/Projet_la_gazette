-- Les contrôles de qualité : un fait vérifié sur les vraies données, après chaque passage.
CREATE TABLE controles (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    passage   timestamptz NOT NULL,
    controle  text NOT NULL,                    -- ex. C01_aucune_date_future
    ok        boolean NOT NULL,
    valeur    double precision,
    seuil     double precision,
    detail    text
);

CREATE INDEX controles_controle_passage ON controles (controle, passage DESC);
