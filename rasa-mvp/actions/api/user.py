from typing import Any, Text, Dict, List, Optional

import requests

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet

from actions import config


class ActionGetUserInfo(Action):

    def name(self) -> Text:
        return "action_get_user_info"

    def _fetch_user_by_id(self, user_id: int) -> Optional[Dict]:
        try:
            response = requests.get(f"{config.API_USERS_URL}/{user_id}", timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            return None

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        # Recupere l'ID depuis le slot
        user_id = tracker.get_slot("user_id")

        if not user_id:
            dispatcher.utter_message(
                text="Je n'ai pas compris quel utilisateur vous recherchez. "
                     "Pouvez-vous me donner son ID (entre 1 et 10) ?"
            )
            return []

        # Validation de l'ID
        try:
            user_id_int = int(user_id)
            if user_id_int < 1 or user_id_int > 10:
                dispatcher.utter_message(
                    text="L'ID doit etre compris entre 1 et 10."
                )
                return [SlotSet("user_id", None)]
        except ValueError:
            dispatcher.utter_message(
                text="L'ID doit etre un nombre entre 1 et 10."
            )
            return [SlotSet("user_id", None)]

        # Appel a l'API
        user = self._fetch_user_by_id(user_id_int)

        if user is None:
            dispatcher.utter_message(
                text="Desole, je n'arrive pas a contacter le service externe. "
                     "Veuillez reessayer plus tard."
            )
            return [SlotSet("user_id", None)]

        # Affichage des informations
        name = user.get("name", "Inconnu")
        username = user.get("username", "Inconnu")
        email = user.get("email", "Non disponible")
        phone = user.get("phone", "Non disponible")
        company = user.get("company", {}).get("name", "Non disponible")

        message = (
            f"Voici les informations de l'utilisateur {user_id}\n\n"
            f"Nom : {name}\n"
            f"Username : {username}\n"
            f"Email : {email}\n"
            f"Telephone : {phone}\n"
            f"Entreprise : {company}"
        )
        dispatcher.utter_message(text=message)

        # Reinitialise le slot apres utilisation
        return [SlotSet("user_id", None)]
