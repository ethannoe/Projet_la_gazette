-- Évaluation des runs et registre des versions du regroupement.
ALTER TABLE runs ADD COLUMN evaluation jsonb;
ALTER TABLE runs ADD COLUMN verdict text CHECK (verdict IN ('revue', 'candidat', 'recale'));

CREATE TABLE versions_modele (
    version       text PRIMARY KEY,
    run_id        text REFERENCES runs(run_id) ON DELETE SET NULL,
    statut        text NOT NULL CHECK (statut IN ('production', 'candidate', 'archivee')),
    configuration jsonb NOT NULL,
    hash_parametres text NOT NULL,
    promue_le     timestamptz,
    par_qui       text NOT NULL,
    creee_le      timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX une_version_production ON versions_modele ((statut))
    WHERE statut = 'production';

CREATE TABLE historique_promotions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    version     text NOT NULL REFERENCES versions_modele(version),
    action      text NOT NULL CHECK (action IN ('promotion', 'retour_arriere', 'initialisation')),
    precedente  text,
    faite_le    timestamptz NOT NULL DEFAULT now(),
    par_qui     text NOT NULL
);

CREATE TABLE relectures_modeles (
    run_id       text PRIMARY KEY REFERENCES runs(run_id) ON DELETE CASCADE,
    decision     text NOT NULL CHECK (decision IN ('approuve', 'recale')),
    echantillon  jsonb NOT NULL,
    commentaire text NOT NULL,
    par_qui      text NOT NULL,
    relu_le      timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE VIEW themes_du_jour AS
SELECT t.*, r.debut AS run_debut
FROM themes t JOIN runs r USING (run_id)
WHERE r.run_id = (
    SELECT run_id FROM runs
    WHERE statut = 'ok' AND declencheur <> 'ci'
      AND coalesce(verdict, 'candidat') <> 'recale'
    ORDER BY debut DESC LIMIT 1
);
