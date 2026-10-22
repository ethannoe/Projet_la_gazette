-- État de chaque source : ce que la collecte sait d'elle d'un passage à l'autre.
CREATE TABLE sources (
    id                  text PRIMARY KEY,                -- id de sources.csv (ex. lemonde)
    nom                 text NOT NULL,
    type                text NOT NULL CHECK (type IN ('PQN', 'PQR')),
    url_flux            text NOT NULL,
    actif               boolean NOT NULL DEFAULT true,   -- false = en sommeil
    derniere_reussite   timestamptz,
    echecs_consecutifs  integer NOT NULL DEFAULT 0,
    etag                text,                            -- pour If-None-Match
    last_modified       text,                            -- pour If-Modified-Since
    derniere_erreur     text,
    mise_en_sommeil_le  timestamptz
);
