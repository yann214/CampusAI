-- Table des documents téléchargeables (PDF / Word) rangés dans data/files/
-- avec leurs sous-dossiers. Sert UNIQUEMENT à la route /documents/chat
-- (recherche par intention explicite "je veux tel document"), séparée du
-- pipeline RAG (data/documents/ + ChromaDB).
--
-- À exécuter une fois sur ta base MySQL :
--   mysql -u root -p univ_douala_fs < data/database/create_table_documents.sql

CREATE TABLE IF NOT EXISTS `documents` (
  `id` INT NOT NULL ,
  `nom_original` VARCHAR(255) NOT NULL ,
  `nom_fichier` VARCHAR(255) NOT NULL ,
  `sous_dossier` VARCHAR(255) DEFAULT NULL ,
  `chemin_relatif` VARCHAR(500) NOT NULL ,
  `type_fichier` VARCHAR(10) DEFAULT NULL ,
  `description` TEXT DEFAULT NULL ,
  `tags` VARCHAR(500) DEFAULT NULL ,
  `date_ajout` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),

  FULLTEXT KEY `ft_recherche` (`nom_original`, `description`, `tags`)
);
