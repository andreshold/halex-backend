import streamlit as st
from halex_core_supabase import poser_question

# Configuration de la page (titre de l'onglet, icône)
st.set_page_config(page_title="Halex — Assistant juridique", page_icon="⚖️")

st.title("⚖️ Halex")
st.caption("Assistant juridique — Constitution haïtienne de 1987 amendée")

# Avertissement légal visible en permanence (essentiel pour une app de droit)
st.info(
    "ℹ️ **Halex vous informe, il ne vous conseille pas.**\n\n"
    "Il explique ce que dit la loi à titre purement informatif, et ne "
    "remplace pas un avocat ou un professionnel du droit pour votre "
    "situation personnelle.\n\n"
    "📖 **Périmètre actuel :** Constitution de 1987 amendée (2011) "
    "uniquement. Les autres textes (Code Civil, Code Pénal, lois, décrets) "
    "ne sont pas encore couverts.\n\n"
    "⏱️ Les lois évoluent : vérifiez toujours qu'un texte est à jour "
    "auprès d'une source officielle."
)

# Le champ de saisie de la question
question = st.text_input("Posez votre question sur la Constitution :")

# Quand l'utilisateur clique sur le bouton
if st.button("Demander à Halex") and question:
    with st.spinner("Halex consulte la Constitution..."):
        resultat = poser_question(question)  # ← on appelle le MOTEUR

    st.markdown("### Réponse")
    st.write(resultat["reponse"])

    st.markdown("### Articles consultés")
    for s in resultat["sources"]:
        st.markdown(f"- **{s['article']}** — {s['contexte']}")

    # Rappel légal SOUS chaque réponse (dans le if : indenté de 4 espaces)
    st.divider()
    st.caption(
        "⚖️ Réponse générée à partir de la Constitution de 1987 amendée, "
        "à titre informatif. Ceci n'est pas un conseil juridique. "
        "Pour votre cas précis, consultez un professionnel du droit."
    )