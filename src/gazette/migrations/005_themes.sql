-- Thèmes du jour (TD 5) : vecteurs en cache, runs tracés, thèmes et rattachements.

-- Cache des embeddings : un vecteur par article et par modèle (nom@révision).
CREATE TABLE embeddings (
    item_id     text NOT NULL REFERENCES articles_propres (item_id) ON DELETE CASCADE,
    modele      text NOT NULL,                  -- ex. sentence-transformers/…@faf4aa42…
    texte_hash  text NOT NULL,                  -- empreinte du texte vectorisé
    vecteur     real[] NOT NULL,
    calcule_le  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (item_id, modele)
);

-- Un run de regroupement : ses données, ses paramètres, ses métriques, ses artefacts.
CREATE TABLE runs (
    run_id           text PRIMARY KEY,          -- ex. 20261023T143000Z-3fa2c1
    debut            timestamptz NOT NULL,
    duree_s          double precision,
    statut           text NOT NULL CHECK (statut IN ('en_cours', 'ok', 'echec')),
    declencheur      text NOT NULL,             -- pipeline ou manuel
    fenetre_debut    timestamptz NOT NULL,
    fenetre_fin      timestamptz NOT NULL,
    nb_articles      integer NOT NULL,
    hash_entree      text NOT NULL,             -- empreinte des articles (id + texte)
    modele           text NOT NULL,
    modele_version   text NOT NULL,             -- révision du modèle sur Hugging Face
    algorithme       text NOT NULL,
    parametres       jsonb NOT NULL,            -- config/clustering.yaml en entier
    hash_parametres  text NOT NULL,
    code_version     text NOT NULL,             -- commit git de l'image
    metriques        jsonb,
    artefacts        jsonb,                     -- fichiers produits (runs/<run_id>/…)
    erreur           text
);

CREATE INDEX runs_debut ON runs (debut DESC);

CREATE TABLE themes (
    theme_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id     text NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    numero     integer NOT NULL,                -- étiquette du thème dans ce run (0 = le plus gros)
    nom        text NOT NULL,
    mots_cles  text[] NOT NULL,
    taille     integer NOT NULL,
    UNIQUE (run_id, numero)
);

CREATE TABLE articles_themes (
    run_id       text NOT NULL REFERENCES runs (run_id) ON DELETE CASCADE,
    item_id      text NOT NULL REFERENCES articles_propres (item_id) ON DELETE CASCADE,
    theme_id     bigint NOT NULL REFERENCES themes (theme_id) ON DELETE CASCADE,
    probabilite  double precision,              -- force du rattachement selon HDBSCAN (0 à 1)
    PRIMARY KEY (run_id, item_id)
);

CREATE INDEX articles_themes_theme ON articles_themes (theme_id);

-- Les thèmes du jour : ceux du dernier run réussi.
CREATE VIEW themes_du_jour AS
SELECT t.*, r.debut AS run_debut
FROM themes t JOIN runs r USING (run_id)
WHERE r.run_id = (SELECT run_id FROM runs WHERE statut = 'ok' ORDER BY debut DESC LIMIT 1);
