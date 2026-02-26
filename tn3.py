""" A small program that retrieves information on global earthquakes from a website. On startup, it loads the data from a local file if one exists. Then, it retrieves the data from the website and creates a JSON file if one is not available. With each update, whether manual or automatic, the data is saved to the JSON file. The data is updated hourly from the website, but a manual update button is also available on the webpage. The data is presented in a table where certain columns can be sorted. It is also possible to perform a basic search within the table to filter the results.
"""

import subprocess
import sys
import os
import json
import importlib
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import asyncio
import aiohttp
import aiofiles
from aiohttp import web


# Activating the virtual environment.
DOSSIER_VENV = ".venv"
if not os.path.exists(DOSSIER_VENV):
    print("Création d'un environnement virtuel...")
    subprocess.check_call([sys.executable, "-m", "venv", DOSSIER_VENV])
print(f"Environnement virtuel activé : {DOSSIER_VENV}")

def verif_dependances(fichier_requirements="requirements.txt"):
    """
    Checks and installs the dependencies listed in requirements.txt in the current Python environment.
    Handles read or installation errors without interrupting the program.	
    """

    if not os.path.exists(fichier_requirements):
        print(f"[Info] Aucun fichier {fichier_requirements} trouvé, aucune dépendance à installer.")
        return

    try:
        with open(fichier_requirements, "r", encoding="utf-8") as f:
            packages = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    except Exception as e:
        print(f"[Erreur] Impossible de lire {fichier_requirements} : {e}")
        return

    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
    except Exception as e:
        print(f"[Avertissement] Impossible de mettre à jour pip : {e}")

    for package in packages:
        nom_module = package.split("==")[0]
        try:
            importlib.import_module(nom_module)
        except ImportError:
            print(f"[Info] Installation automatique de {package}...")
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", package])
            except Exception as e:
                print(f"[Erreur] Impossible d’installer {package} : {e}")

def verif_dossier():
    """ A function that allows you to check for the existence of the data folder and creates it if necessary.
    """

    os.makedirs(DOSSIER_DONNEES, exist_ok=True)

async def chargement_tremblements():
    """ Function that allows you to retrieve earthquake data from the website.
    """

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(URL_USGS, timeout=15) as reponse:
                reponse.raise_for_status()
                return await reponse.json()
    except aiohttp.ClientConnectionError:
        print("Erreur : impossible de se connecter au serveur.")
    except aiohttp.ClientResponseError as e:
        print(f"Erreur HTTP {e.status} : {e.message}")
    except asyncio.TimeoutError:
        print("Erreur : la requête a dépassé le délai autorisé.")
    except Exception as e:
        print(f"Erreur inattendue pendant le téléchargement : {e}")
    return None

async def sauvegarde_json(donnees):
    """ This function saves the data to a JSON file. The file is created if it does not already exist.
    """
    
    verif_dossier()
    async with aiofiles.open(FICHIER_DONNEES, "w") as f:
        await f.write(json.dumps(donnees, indent=2))

async def chargement_json():
    """ This function loads data from a JSON file.
	It returns an empty structure if the file doesn't exist or if the JSON is invalid.
    """

    try:
        async with aiofiles.open(FICHIER_DONNEES, "r") as f:
            contenu = await f.read()
            return json.loads(contenu)
    except json.JSONDecodeError:
        print("[Erreur] Format JSON invalide.")
        return {"features": []}
    except Exception as e:
        print(f"[Erreur] Impossible de lire le fichier : {e}")
        return {"features": []}

def extract_evenements(evenement):
    """ A function that allows you to extract JSON data and separate it properly.
    """
    
    propriete = evenement.get("properties", {})
    marque_temps = propriete.get("time")
    
    if marque_temps:
        date_temps = datetime.fromtimestamp(marque_temps / 1000)
        moment_str = date_temps.strftime("%a %d %b %Y %H:%M:%S")
    else:
        moment_str = ""
    
    return {
        "endroit": propriete.get("place", "Unknown"),
        "magnitude": propriete.get("mag", 0),
        "moment": moment_str,
        "url": propriete.get("url", "")
    }

def trie_evenements(evenements, trier_par="magnitude", ordre="descendant"):
    """ Function that allows you to sort the data for display in the table.
    """

    inverse = (ordre == "descendant")
    key_map = {
        "magnitude": lambda e: e["magnitude"] or 0,
        "endroit": lambda e: e["endroit"] or "",
        "moment": lambda e: e["moment"] or ""
    }
    fonction_cle = key_map.get(trier_par, key_map["magnitude"])
    return sorted(evenements, key=fonction_cle, reverse=inverse)

async def page_web(requete):
    """ A function that allows the web page to be built properly.
    """

    trier_par = requete.query.get("tri", "moment")
    ordre = requete.query.get("ordre", "descendant")
    donnees = await chargement_json()

    evenements = list(map(extract_evenements, donnees.get("features", [])))
    evenements = list(filter(lambda e: e['magnitude'] > 0.1, evenements))
    evenements = trie_evenements(evenements, trier_par=trier_par, ordre=ordre)
    inverser_ordre = lambda col: "ascendant" if trier_par == col and ordre == "descendant" else "descendant"

    html_rows = [
        f"<tr><td>{e['magnitude']}</td><td>{e['endroit']}</td><td>{e['moment']}</td>"
        f"<td><a href='{e['url']}' target='_blank'>Liens vers earthquake.usgs.gov</a></td></tr>"
        for e in evenements
    ]

    html = f"""
    <html>
    <head>
        <title>Tremblements de terre mondiaux</title>
        <meta http-equiv="refresh" content="3600">
        <style>
            table {{ border-collapse: collapse; width: 100%; }}
            th, td {{ border: 1px solid black; padding: 5px; text-align: left; }}
            th a {{ text-decoration: none; color: black; }}
        </style>
    </head>
    <body>
        <h1>🌎 Tremblements de terre mondiaux (dans les 24 dernières heures) 🌎</h1>
        <p>Nombre total d'évènements: {len(evenements)}</p>
        <button onclick="location.href='/update'" style="display: block; margin-bottom: 20px;">Mettre à jour</button>
        <label for="entree_recherche">Recherche rapide:</label>
        <input type="text" id="entree_recherche" placeholder="Écrire ici pour chercher...">
        <select id="selection_colonne">
            <option value="1" selected>Endroit</option>
            <option value="0">Magnitude</option>
            <option value="2">Moment</option>
        </select>
        <table>
            <tr>
                <th><a href='/?tri=magnitude&ordre={inverser_ordre("magnitude")}'>Magnitude</a></th>
                <th><a href='/?tri=endroit&ordre={inverser_ordre("endroit")}'>Endroit</a></th>
                <th><a href='/?tri=moment&ordre={inverser_ordre("moment")}'>Moment</a></th>
                <th>Détails</th>
            </tr>
            {''.join(html_rows)}
        </table>
    <script>

    // For searching within the table.
    const entree_recherche = document.getElementById("entree_recherche");
    const selection_colonne = document.getElementById("selection_colonne");
    const tableau = document.querySelector("table");

    entree_recherche.addEventListener("input", filtrer_tableau);
    selection_colonne.addEventListener("change", filtrer_tableau);

    function filtrer_tableau() {{
        const terme = entree_recherche.value.toLowerCase();
        const index_colonne = parseInt(selection_colonne.value);

        const ligne = tableau.querySelectorAll("tr");
        ligne.forEach((ligne, i) => {{
            if(i === 0) return;
            const cell = ligne.cells[index_colonne];
            ligne.style.display = cell.textContent.toLowerCase().includes(terme) ? "" : "none";
        }});
    }}
    </script>

    </body>
    </html>
    """
    return web.Response(text=html, content_type="text/html")

async def maj_manuelle(requete):
    """ Function that allows for manual data updates.
    """

    print(f"[{datetime.now().strftime('%a %d %b %Y %H:%M:%S')}] Mise à jour manuelle déclenchée.")
    donnees = await chargement_tremblements()
    if donnees:
        await sauvegarde_json(donnees)
    else:
        print("Échec de la mise à jour manuelle : aucune donnée reçue.")
    raise web.HTTPFound("/")

async def maj_auto():
    """ Function that allows for automatic data updates.
    """

    while True:
        print(f"[{datetime.now().strftime('%a %d %b %Y %H:%M:%S')}] Mise à jour automatique des données...")
        donnees = await chargement_tremblements()
        if donnees:
            await sauvegarde_json(donnees)
            evenements = [extract_evenements(e) for e in donnees.get("features", []) if e.get("properties", {}).get("mag", 0) > 0.1]
            print(f"[{datetime.now().strftime('%a %d %b %Y %H:%M:%S')}] Mise à jour terminée ({len(evenements)} évènements).")
        else:
            print("Aucune donnée reçue, tentative à la prochaine heure.")
        await asyncio.sleep(PERIODE_MAJ)

async def demarrage_taches(app):
    """ Update startup function.
    """

    donnees = await chargement_json()
    nouvelles_donnees = await chargement_tremblements()
    if nouvelles_donnees:
        await sauvegarde_json(nouvelles_donnees)
        donnees = nouvelles_donnees
    print(f"[{datetime.now(timezone.utc).isoformat()}] Chargement initial des données complété.")
    app['maj_tache'] = asyncio.create_task(maj_auto())

async def fermeture_taches(app):
    """ Function to stop updates.
    """

    tache = app.get('maj_tache')
    if tache:
        tache.cancel()
        try:
            await tache
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"Erreur inattendue pendant la fermeture de la tâche : {e}")

async def initialisation():
    """ Initialization function.
    """

    app = web.Application()
    app.router.add_get("/", page_web)
    app.router.add_get("/update", maj_manuelle)

    app.on_startup.append(demarrage_taches)
    app.on_cleanup.append(fermeture_taches)
    return app

# Dependency check.
verif_dependances()

# Declaration of global constants and variables.
DOSSIER_DONNEES = "Données"
FICHIER_DONNEES = os.path.join(DOSSIER_DONNEES, "Tremblements_terre.json")
URL_USGS = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_day.geojson"
PORT = 8080
PERIODE_MAJ = 3600
local_tz = ZoneInfo("America/Toronto")

if __name__ == "__main__":
    verif_dossier()
    web.run_app(initialisation(), port=PORT)