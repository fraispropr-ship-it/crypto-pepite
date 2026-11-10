# Radar Ordres — le bouton « Prendre » des alertes

Quand le Radar Alt envoie une alerte, deux boutons apparaissent sous le message :
**✅ Prendre** et **❌ Ignorer**. « Prendre » demande une confirmation, puis « Confirmer »
passe l'ordre sur Zoomex : entrée au marché, SL et TP du ticket, quantité calculée pour
risquer le montant choisi (1 USDT par défaut).

Ce dossier contient le petit service (worker Cloudflare) qui reçoit l'appui sur le bouton.

## Ce qu'il vérifie avant de passer un ordre

- seul ton compte Telegram peut appuyer ;
- le prix est encore proche de l'entrée du signal (entre −0,5 R et +0,3 R), sinon refus ;
- pas déjà une position sur la paire, et 3 positions ouvertes au maximum ;
- le signal a moins de 24 h ;
- un même message ne peut passer qu'un seul ordre.

Le résultat (ordre passé ou raison du refus) arrive en réponse dans Telegram.

## Installation (une seule fois)

Tout se fait depuis un navigateur ; aucun ordinateur n'est nécessaire.

1. **Créer un bot Telegram dédié.** Dans Telegram, écris à `@BotFather`, envoie `/newbot`,
   choisis un nom (par exemple « Radar Ordres »). Il te donne un jeton. Ouvre ensuite la
   conversation avec ton nouveau bot et appuie sur **Démarrer**.
   Un bot dédié est obligatoire : le bot actuel est lu par Crypto Pépite et la météo, et
   Telegram n'accepte pas les deux modes de lecture sur un même bot.
2. **Créer les clés Zoomex de TEST.** Sur le site de test de Zoomex (`testnet.zoomex.com`),
   crée un compte, puis une clé API avec le droit « contrats / trade » uniquement.
3. **Créer un jeton Cloudflare.** Tableau de bord Cloudflare → Mon profil → Jetons d'API →
   Créer → modèle « Modifier Cloudflare Workers ». Note aussi ton identifiant de compte
   (page Workers, colonne de droite).
4. **Ajouter les secrets GitHub** (dépôt → Settings → Secrets and variables → Actions) :

   | Secret | Valeur |
   |---|---|
   | `RADAR_TELEGRAM_TOKEN` | jeton du nouveau bot |
   | `CLOUDFLARE_API_TOKEN` | jeton Cloudflare |
   | `CLOUDFLARE_ACCOUNT_ID` | identifiant de compte Cloudflare |
   | `ZOOMEX_TEST_API_KEY` | clé API du compte de test |
   | `ZOOMEX_TEST_API_SECRET` | secret API du compte de test |

5. **Déployer.** Onglet Actions → « Radar Ordres - déployer » → Run workflow, mode `test`.
   Le bot t'écrit « Radar Ordres installé ».
6. **Essayer.** Envoie `/test` au bot : un faux signal arrive avec les boutons. Appuie sur
   « Prendre » puis « Confirmer » et vérifie la position sur le compte de test.

Dès que `RADAR_TELEGRAM_TOKEN` existe, le radar envoie ses messages via le nouveau bot,
avec les boutons. Fais donc les étapes 4 et 5 à la suite.

## Passer en réel

Quand les essais sont concluants :

1. Sur Zoomex (compte réel), crée une clé API : droit **trade sur les contrats uniquement,
   jamais le retrait**.
2. Ajoute les secrets `ZOOMEX_API_KEY` et `ZOOMEX_API_SECRET`.
3. Relance « Radar Ordres - déployer » en mode `reel`, avec le risque par ordre voulu.

## Au quotidien

- `/etat` : mode (test ou réel), positions ouvertes.
- `/test` : faux signal pour vérifier que tout marche (en mode réel, confirmer passe un
  vrai petit ordre).
- Changer le risque ou le nombre de positions : relancer le déploiement avec d'autres valeurs.
- Tout couper : dans Cloudflare, variable `ORDRES_ACTIFS` = `false` sur le worker
  `radar-ordres` ; ou supprimer le secret `RADAR_TELEGRAM_TOKEN` pour revenir aux alertes
  sans bouton sur l'ancien bot.

## Limites connues

- Le compte doit être en mode « sens unique » (one-way), pas en mode couverture.
- Sur le compte de test, les prix diffèrent du réel : le service garde les mêmes écarts
  en pourcentage autour du prix de test.
- Si une clé API sans adresse IP liée expire (Zoomex peut la limiter dans le temps),
  il faut la recréer et relancer le déploiement.
- Le SL et le TP sont posés avec l'ordre ; la durée maximale de 7 jours du radar n'est
  pas appliquée automatiquement : c'est à toi de clôturer.

## Tests

```
cd ordres && npm test
```
