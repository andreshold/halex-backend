

const translations = {

  // ─────────────────────────────────────────
  // FR — Français
  // ─────────────────────────────────────────
  fr: {

    appLayout: {
      title: 'Lajistis AI — Dwa ou, nan men ou',
      description:
        "Lajistis AI, l'intelligence juridique haïtienne à votre service. Assistant légal spécialisé dans le droit haïtien : Constitution, Code Civil, Code Pénal et plus.",
      generator: 'v0.app',
      themeColor: '#050914',
    },

    chatPage: {
      welcome: {
        content:
          "Bonjou! Mwen se Lajistis AI, asistan jiridik ou. Posez-moi vos questions sur le droit haïtien — droit civil, pénal, du travail ou familial — et je vous répondrai avec les articles de loi exacts.",
        sources: [{ article: 'Préambule', code: 'Constitution 1987' }],
      },
      suggestions: [
        "Quels sont mes droits en cas de licenciement ?",
        "Comment se déroule une procédure de divorce ?",
        "Que faire si mon propriétaire m'expulse ?",
        "Quels sont mes droits lors d'une garde à vue ?",
      ],
      sampleAnswer: {
        content:
          "En droit haïtien, plusieurs protections s'appliquent à votre situation. Le contrat ne peut être rompu sans motif légitime, et un préavis ainsi qu'une indemnité peuvent vous être dus. Voici les références applicables à votre cas.",
        sources: [
          { article: 'Art. 45', code: 'Code du Travail' },
          { article: 'Art. 1134', code: 'Code Civil' },
        ],
      },
      header: {
        assistant: 'Assistant Juridique',
        online: 'En ligne',
        back: 'Accueil',
        openMenu: 'Ouvrir le menu',
      },
      suggestionsHeading: 'Questions suggérées',
    },

    authModal: {
      closeWindow: 'Fermer la fenêtre',
      closeLabel: 'Fermer',
      createAccount: 'Créer un compte',
      welcomeBack: 'Bon retour',
      join: 'Rejoignez des milliers de citoyens haïtiens.',
      access: 'Accédez à votre assistant juridique.',
      emailLabel: 'Adresse email',
      passwordLabel: 'Mot de passe',
      createAccountCta: 'Créer mon compte',
      signInCta: 'Se connecter',
      or: 'ou',
      continueWithGoogle: 'Continuer avec Google',
      signUpTab: 'Inscription',
      signInTab: 'Connexion',
    },

    chatInput: {
      voiceLabel: 'Entrée vocale',
      placeholder: 'Décrivez votre situation juridique...',
      sendLabel: 'Envoyer',
      disclaimer:
        'Lajistis AI fournit des informations juridiques, pas de conseil légal professionnel.',
    },

    chatSidebar: {
      categoriesTitle: 'Catégories',
      categories: ['Droit Civil', 'Droit Pénal', 'Travail', 'Famille'],
      historyTitle: 'Conversations',
      history: [
        'Procédure de divorce en Haïti',
        'Droits du locataire',
        'Contrat de travail rompu',
        'Héritage et succession',
        'Plainte pour diffamation',
      ],
      newQuestion: 'Nouvelle Question',
      searchPlaceholder: 'Rechercher...',
      closeMenu: 'Fermer le menu',
    },

    message: {
      highConfidence: 'Confiance élevée',
      lajistisScore: 'Lajistis Score',
      copy: 'Copier',
      share: 'Partager',
      useful: 'Utile',
      notUseful: 'Pas utile',
    },

    documentsPage: {
      sectionLabel: 'Bibliothèque',
      heading: 'Explorez les textes de loi',
      description:
        "Recherchez à travers les documents juridiques fondamentaux d'Haïti.",
      searchPlaceholder: 'Rechercher dans tous les documents...',
      tabs: ['Tous', 'Civil', 'Pénal', 'Commercial', 'Travail'] as const,
      exploreButton: 'Explorer',
      noResults: 'Aucun document trouvé.',
    },

    featuresPage: {
      sectionLabel: 'Fonctionnalités',
      heading: 'Tout le droit haïtien, en un seul endroit',
      description:
        "Une intelligence entraînée sur les textes de loi haïtiens pour vous guider à chaque étape.",
      cards: [
        {
          title: 'Droit Civil',
          desc: 'Famille, propriété, contrats. Des réponses claires sur vos droits civils.',
        },
        {
          title: 'Droit Pénal',
          desc: 'Infractions, procédures, défense. Comprenez vos droits face à la justice.',
        },
        {
          title: 'Droit du Travail',
          desc: 'Emploi, licenciements, droits. Protégez votre vie professionnelle.',
        },
        {
          title: 'Multilingue',
          desc: 'Français, Créole et Anglais. La justice dans votre langue.',
        },
        {
          title: 'Réponses Sourcées',
          desc: "Citations d'articles de loi exacts pour chaque réponse fournie.",
        },
        {
          title: 'Disponible 24/7',
          desc: 'Toujours accessible, où que vous soyez, à tout moment.',
        },
      ],
    },

    footerPage: {
      columns: [
        {
          title: 'Produit',
          links: ['Fonctionnalités', 'Documents', 'Tarifs', 'API'],
        },
        {
          title: 'Légal',
          links: ['Conditions', 'Confidentialité', 'Mentions légales', 'Cookies'],
        },
        {
          title: 'Support',
          links: ["Centre d'aide", 'Contact', 'Statut', 'FAQ'],
        },
        {
          title: 'Communauté',
          links: ['Blog', 'Discord', 'Partenaires', 'Carrières'],
        },
      ],
      description:
        "Dwa ou, nan men ou. L'intelligence juridique haïtienne au service de millions de citoyens.",
      socialLabel: 'Réseau social',
      madeWith: 'Fait avec',
      forHaiti: 'pour Haïti',
      copyright: (year: number) => `© ${year} Lajistis AI. Tous droits réservés.`,
    },

    heroPage: {
      badgeLabels: ['Constitution Haïtienne', 'Code Civil', 'Code Pénal'],
      promoLabel: "L'intelligence juridique haïtienne",
      headline: 'Dwa ou, nan men ou.',
      description:
        "L'intelligence juridique haïtienne à votre service. Des réponses claires et sourcées sur vos droits, 24h/24.",
      primaryCta: 'Commencer Gratuitement',
      demoCta: 'Voir une Démo',
      discover: 'Découvrir',
      scrollAria: 'Faire défiler vers le bas',
    },

    languageSwitcher: {
      ariaLabel: 'Sélecteur de langue',
      langs: ['FR', 'KR', 'EN'] as const,
    },

    navbar: {
      links: [
        { label: 'Accueil', href: '#accueil' },
        { label: 'Fonctionnalités', href: '#fonctionnalites' },
        { label: 'Documents', href: '#documents' },
        { label: 'Tarifs', href: '#tarifs' },
      ],
      login: 'Se Connecter',
      start: 'Commencer',
      openMenu: 'Ouvrir le menu',
      closeMenu: 'Fermer le menu',
    },

    pricingPage: {
      sectionLabel: 'Tarifs',
      heading: 'Un plan pour chaque citoyen',
      monthlyLabel: 'Mensuel',
      annualLabel: 'Annuel',
      discountLabel: '-20%',
      tiers: [
        {
          name: 'Citoyen',
          tagline: 'Pour découvrir vos droits',
          cta: 'Commencer Gratuitement',
          features: [
            '5 questions par jour',
            'Accès Constitution & Code Civil',
            'Réponses sourcées',
            'Support communautaire',
          ],
        },
        {
          name: 'Professionnel',
          tagline: 'Pour un usage intensif',
          cta: 'Passer Pro',
          features: [
            'Questions illimitées',
            'Tous les codes de loi',
            'Recherche avancée par article',
            'Historique illimité',
            'Réponses prioritaires',
            'Support par email',
          ],
          popularBadge: 'Le plus populaire',
        },
        {
          name: 'Cabinet Juridique',
          tagline: 'Pour les professionnels du droit',
          cta: 'Contacter les ventes',
          features: [
            'Tout du plan Pro',
            'Accès API complet',
            'Comptes multi-utilisateurs',
            'Intégrations sur mesure',
            'Gestionnaire dédié',
          ],
        },
      ],
      perMonth: '/mois',
    },

    urgenceButton: {
      ariaLabel: 'Urgence juridique',
      label: 'Urgence Juridique',
    },

    techStack: {
      poweredBy: 'Propulsé par',
      items: [
        'Claude AI',
        'LangChain',
        'Constitution Haïtienne 1987',
        'Code Civil',
        'Code Pénal',
        'Code du Travail',
        'RAG Juridique',
      ],
    },

  },

  // ─────────────────────────────────────────
  // HT — Kreyòl Ayisyen
  // ─────────────────────────────────────────
  ht: {

    appLayout: {
      title: 'Lajistis AI — Dwa ou, nan men ou',
      description:
        "Lajistis AI, entèlijans jiridik ayisyen an nan sèvis ou. Asistan legal espesyalize nan dwa ayisyen : Konstitisyon, Kòd Sivil, Kòd Penal ak plis.",
      generator: 'v0.app',
      themeColor: '#050914',
    },

    chatPage: {
      welcome: {
        content:
          "Bonjou! Mwen se Lajistis AI, asistan jiridik ou. Poze m kesyon ou yo sou dwa ayisyen — dwa sivil, penal, travay oswa fanmi — epi m ap reponn ou ak atik lwa egzak yo.",
        sources: [{ article: 'Preambil', code: 'Konstitisyon 1987' }],
      },
      suggestions: [
        "Ki dwa mwen genyen si yo revoke m nan travay ?",
        "Kijan yon pwosedi divòs fèt ?",
        "Kisa pou m fè si pwopriyetè m ap chase m ?",
        "Ki dwa mwen genyen lè yo mete m nan gad avèl ?",
      ],
      sampleAnswer: {
        content:
          "Nan dwa ayisyen, gen plizyè pwoteksyon ki aplike pou sitiyasyon ou a. Kontra a pa kapab kase san rezon valab, epi yon preyavi ak yon endomite ka dwe ou. Men referans ki aplike pou ka ou a.",
        sources: [
          { article: 'Atik 45', code: 'Kòd Travay' },
          { article: 'Atik 1134', code: 'Kòd Sivil' },
        ],
      },
      header: {
        assistant: 'Asistan Jiridik',
        online: 'Anliy',
        back: 'Akèy',
        openMenu: 'Ouvri meni an',
      },
      suggestionsHeading: 'Kesyon yo sijere',
    },

    authModal: {
      closeWindow: 'Fèmen fenèt la',
      closeLabel: 'Fèmen',
      createAccount: 'Kreye yon kont',
      welcomeBack: 'Byenvini tounen',
      join: 'Rantre nan kominote milye sitwayen ayisyen yo.',
      access: 'Jwenn aksè nan asistan jiridik ou a.',
      emailLabel: 'Adrès imèl',
      passwordLabel: 'Modpas',
      createAccountCta: 'Kreye kont mwen',
      signInCta: 'Konekte',
      or: 'oswa',
      continueWithGoogle: 'Kontinye ak Google',
      signUpTab: 'Enskrisyon',
      signInTab: 'Koneksyon',
    },

    chatInput: {
      voiceLabel: 'Antre vwa',
      placeholder: 'Dekri sitiyasyon jiridik ou a...',
      sendLabel: 'Voye',
      disclaimer:
        "Lajistis AI bay enfòmasyon jiridik, li pa ranplase konsèy yon avoka pwofesyonèl.",
    },

    chatSidebar: {
      categoriesTitle: 'Kategori',
      categories: ['Dwa Sivil', 'Dwa Penal', 'Travay', 'Fanmi'],
      historyTitle: 'Konvèsasyon',
      history: [
        'Pwosedi divòs ann Ayiti',
        'Dwa lokatè a',
        'Kontra travay kase',
        'Eritaj ak siksesyon',
        'Plent pou difamasyon',
      ],
      newQuestion: 'Nouvo Kesyon',
      searchPlaceholder: 'Chèche...',
      closeMenu: 'Fèmen meni an',
    },

    message: {
      highConfidence: 'Konfyans wo',
      lajistisScore: 'Lajistis Score',
      copy: 'Kopye',
      share: 'Pataje',
      useful: 'Itil',
      notUseful: 'Pa itil',
    },

    documentsPage: {
      sectionLabel: 'Bibliyotèk',
      heading: 'Eksplore tèks lwa yo',
      description:
        "Chèche nan dokiman jiridik fondamantal Ayiti yo.",
      searchPlaceholder: 'Chèche nan tout dokiman yo...',
      tabs: ['Tout', 'Sivil', 'Penal', 'Komèsyal', 'Travay'] as const,
      exploreButton: 'Eksplore',
      noResults: 'Pa gen okenn dokiman jwenn.',
    },

    featuresPage: {
      sectionLabel: 'Fonksyonalite',
      heading: 'Tout dwa ayisyen an, nan yon sèl kote',
      description:
        "Yon entèlijans fòme sou tèks lwa ayisyen yo pou gide ou nan chak etap.",
      cards: [
        {
          title: 'Dwa Sivil',
          desc: 'Fanmi, pwopriyete, kontra. Repons klè sou dwa sivil ou yo.',
        },
        {
          title: 'Dwa Penal',
          desc: 'Enfrasyon, pwosedi, defans. Konprann dwa ou devan jistis la.',
        },
        {
          title: 'Dwa Travay',
          desc: 'Travay, revokasyon, dwa. Pwoteje vi pwofesyonèl ou.',
        },
        {
          title: 'Multilang',
          desc: 'Franse, Kreyòl ak Anglè. Jistis nan lang ou.',
        },
        {
          title: 'Repons ak Sous',
          desc: "Sitasyon atik lwa egzak pou chak repons bay.",
        },
        {
          title: 'Disponib 24/7',
          desc: 'Toujou aksesib, kote ou ye a, nenpòt ki lè.',
        },
      ],
    },

    footerPage: {
      columns: [
        {
          title: 'Pwodwi',
          links: ['Fonksyonalite', 'Dokiman', 'Pri', 'API'],
        },
        {
          title: 'Legal',
          links: ['Kondisyon', 'Konfidansyalite', 'Avètisman legal', 'Cookies'],
        },
        {
          title: 'Sipò',
          links: ["Sant èd", 'Kontak', 'Estati', 'FAQ'],
        },
        {
          title: 'Kominote',
          links: ['Blog', 'Discord', 'Patnè', 'Karyè'],
        },
      ],
      description:
        "Dwa ou, nan men ou. Entèlijans jiridik ayisyen an nan sèvis milyon sitwayen.",
      socialLabel: 'Rezo sosyal',
      madeWith: 'Fèt ak',
      forHaiti: 'pou Ayiti',
      copyright: (year: number) => `© ${year} Lajistis AI. Tout dwa rezève.`,
    },

    heroPage: {
      badgeLabels: ['Konstitisyon Ayisyen', 'Kòd Sivil', 'Kòd Penal'],
      promoLabel: "Entèlijans jiridik ayisyen an",
      headline: 'Dwa ou, nan men ou.',
      description:
        "Entèlijans jiridik ayisyen an nan sèvis ou. Repons klè ak sous sou dwa ou yo, 24h/24.",
      primaryCta: 'Kòmanse Gratis',
      demoCta: 'Wè yon Demo',
      discover: 'Dekouvri',
      scrollAria: 'Defle vè anba',
    },

    languageSwitcher: {
      ariaLabel: 'Selektè lang',
      langs: ['FR', 'KR', 'EN'] as const,
    },

    navbar: {
      links: [
        { label: 'Akèy', href: '#accueil' },
        { label: 'Fonksyonalite', href: '#fonctionnalites' },
        { label: 'Dokiman', href: '#documents' },
        { label: 'Pri', href: '#tarifs' },
      ],
      login: 'Konekte',
      start: 'Kòmanse',
      openMenu: 'Ouvri meni an',
      closeMenu: 'Fèmen meni an',
    },

    pricingPage: {
      sectionLabel: 'Pri',
      heading: 'Yon plan pou chak sitwayen',
      monthlyLabel: 'Chak mwa',
      annualLabel: 'Anyèl',
      discountLabel: '-20%',
      tiers: [
        {
          name: 'Sitwayen',
          tagline: 'Pou dekouvri dwa ou yo',
          cta: 'Kòmanse Gratis',
          features: [
            '5 kesyon pa jou',
            'Aksè Konstitisyon & Kòd Sivil',
            'Repons ak sous',
            'Sipò kominote',
          ],
        },
        {
          name: 'Pwofesyonèl',
          tagline: 'Pou yon itilizasyon entansif',
          cta: 'Pase Pro',
          features: [
            'Kesyon san limit',
            'Tout kòd lwa yo',
            'Rechèch avanse pa atik',
            'Istorik san limit',
            'Repons priyoritè',
            'Sipò pa imèl',
          ],
          popularBadge: 'Pi popilè',
        },
        {
          name: 'Kabinè Jiridik',
          tagline: 'Pou pwofesyonèl dwa yo',
          cta: 'Kontakte vant yo',
          features: [
            'Tout plan Pro a',
            'Aksè API konplè',
            'Kont milti-itilizatè',
            'Entegrasyon sou mezi',
            'Jesyonè dedye',
          ],
        },
      ],
      perMonth: '/mwa',
    },

    urgenceButton: {
      ariaLabel: 'Ijans jiridik',
      label: 'Ijans Jiridik',
    },

    techStack: {
      poweredBy: 'Pwopulse pa',
      items: [
        'Claude AI',
        'LangChain',
        'Konstitisyon Ayisyen 1987',
        'Kòd Sivil',
        'Kòd Penal',
        'Kòd Travay',
        'RAG Jiridik',
      ],
    },

  },

} as const

// ─────────────────────────────────────────
// Type exports — utilise dans tes composants
// ─────────────────────────────────────────
export type Language = keyof typeof translations  // 'fr' | 'kr'
export type Translations = typeof translations

export default translations