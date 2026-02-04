# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List, Optional
import requests

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted

# URL de l'API externe
API_USERS_URL = "https://jsonplaceholder.typicode.com/users"


class ActionClearTransactionSlots(Action):
    """Réinitialise uniquement les slots de transaction après confirmation/annulation."""

    def name(self) -> Text:
        return "action_clear_transaction_slots"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        # Réinitialise les slots de transaction
        return [
            SlotSet("amount", None),
            SlotSet("phone_number", None),
            SlotSet("neero_id", None),
            SlotSet("currency", None),
        ]


class ActionRestart(Action):
    """Réinitialise complètement la conversation (tous les slots + historique)."""

    def name(self) -> Text:
        return "action_restart"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Conversation réinitialisée. Comment puis-je vous aider ?")
        return [Restarted()]


class ActionGetUserInfo(Action):
    """Récupère les informations d'un utilisateur depuis l'API externe par son ID."""

    def name(self) -> Text:
        return "action_get_user_info"

    def _fetch_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Récupère un utilisateur par son ID depuis l'API."""
        try:
            response = requests.get(f"{API_USERS_URL}/{user_id}", timeout=10)
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

        # Récupère l'ID depuis le slot
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
                    text="L'ID doit être compris entre 1 et 10."
                )
                return [SlotSet("user_id", None)]
        except ValueError:
            dispatcher.utter_message(
                text="L'ID doit être un nombre entre 1 et 10."
            )
            return [SlotSet("user_id", None)]

        # Appel à l'API
        user = self._fetch_user_by_id(user_id_int)

        if user is None:
            dispatcher.utter_message(
                text="Désolé, je n'arrive pas à contacter le service externe. "
                     "Veuillez réessayer plus tard."
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
            f"Téléphone : {phone}\n"
            f"Entreprise : {company}"
        )
        dispatcher.utter_message(text=message)

        # Réinitialise le slot après utilisation
        return [SlotSet("user_id", None)]
