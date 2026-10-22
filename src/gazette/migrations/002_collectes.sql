-- Une ligne par source et par passage : les compteurs de la collecte.
CREATE TABLE collectes (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_id        text NOT NULL REFERENCES sources (id),
    debut            timestamptz NOT NULL,
    duree_ms         integer NOT NULL,
    statut           text NOT NULL CHECK (statut IN ('ok', 'inchange', 'echec')),
    http_status      integer,
    tentatives       integer NOT NULL DEFAULT 0,
    recus            integer NOT NULL DEFAULT 0,
    ecrits           integer NOT NULL DEFAULT 0,
    ignores          integer NOT NULL DEFAULT 0,
    erreur           text,
    mise_en_sommeil  boolean NOT NULL DEFAULT false
);

CREATE INDEX collectes_source_debut ON collectes (source_id, debut DESC);
