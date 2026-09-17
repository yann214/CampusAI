-- Table des documents téléchargeables (PDF / Word) rangés dans data/files/
-- avec leurs sous-dossiers. Sert UNIQUEMENT à la route /documents/chat
-- (recherche par intention explicite "je veux tel document"), séparée du
-- pipeline RAG (data/documents/ + ChromaDB).
--
-- À exécuter une fois sur ta base MySQL :
--   mysql -u root -p univ_douala_fs < data/database/create_table_documents.sql

CREATE TABLE IF NOT EXISTS `documents` (
  `id` INT NOT NULL AUTO_INCREMENT,
  `nom_original` VARCHAR(255) NOT NULL COMMENT 'Nom affiché à l’étudiant, ex: Guide de l’étudiant 2025.pdf',
  `nom_fichier` VARCHAR(255) NOT NULL COMMENT 'Nom réel du fichier sur le disque',
  `sous_dossier` VARCHAR(255) DEFAULT NULL COMMENT 'Sous-dossier dans data/files/, ex: guides, emplois_du_temps',
  `chemin_relatif` VARCHAR(500) NOT NULL COMMENT 'Chemin relatif à FILES_ROOT_DIR, ex: guides/Guide-Etudiant-FS-25.pdf',
  `type_fichier` VARCHAR(10) DEFAULT NULL COMMENT 'pdf ou docx',
  `description` TEXT DEFAULT NULL COMMENT 'Description utilisée pour la recherche par mots-clés',
  `tags` VARCHAR(500) DEFAULT NULL COMMENT 'Mots-clés additionnels séparés par des virgules',
  `date_ajout` TIMESTAMP NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uniq_chemin_relatif` (`chemin_relatif`),
  FULLTEXT KEY `ft_recherche` (`nom_original`, `description`, `tags`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
