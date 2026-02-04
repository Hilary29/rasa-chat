# This files contains your custom actions which can be used to run
# custom Python code.
#
# See this guide on how to implement these action:
# https://rasa.com/docs/rasa/custom-actions

from typing import Any, Text, Dict, List, Optional
import re
import requests

from rasa_sdk import Action, Tracker, FormValidationAction
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet, Restarted
from rasa_sdk.types import DomainDict

# URL de l'API externe
API_USERS_URL = "https://jsonplaceholder.typicode.com/users"


class ValidateTransferForm(FormValidationAction):
    """Valide et gere le formulaire de transfert avec slots dynamiques."""

    def name(self) -> Text:
        return "validate_transfer_form"

    async def required_slots(
        self,
        domain_slots: List[Text],
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> List[Text]:
        """Determine dynamiquement les slots requis selon transfer_type."""

        transfer_type = tracker.get_slot("transfer_type")

        # D'abord on a besoin du type de transfert
        if not transfer_type:
            return ["transfer_type"]

        # Ensuite le montant
        if not tracker.get_slot("amount"):
            return ["transfer_type", "amount"]

        # Puis le destinataire selon le type
        if transfer_type == "neero":
            return ["transfer_type", "amount", "neero_id"]
        elif transfer_type == "mobile_money":
            return ["transfer_type", "amount", "phone_number"]

        # Fallback
        return ["transfer_type", "amount"]

    async def extract_transfer_type(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Extrait transfer_type des entites ou infere depuis d'autres slots."""

        # Verifier si deja defini
        current_transfer_type = tracker.get_slot("transfer_type")
        if current_transfer_type:
            return {"transfer_type": current_transfer_type}

        # Essayer d'extraire depuis les entites
        entities = tracker.latest_message.get("entities", [])

        transfer_type_entity = next(
            (e["value"] for e in entities if e["entity"] == "transfer_type"),
            None
        )

        if transfer_type_entity:
            normalized = self._normalize_transfer_type(transfer_type_entity)
            if normalized:
                return {"transfer_type": normalized}

        # Inferer depuis neero_id
        neero_id = tracker.get_slot("neero_id")
        neero_id_entity = next(
            (e["value"] for e in entities if e["entity"] == "neero_id"),
            None
        )
        if neero_id or neero_id_entity:
            return {"transfer_type": "neero"}

        # Inferer depuis phone_number
        phone_number = tracker.get_slot("phone_number")
        phone_entity = next(
            (e["value"] for e in entities if e["entity"] == "phone_number"),
            None
        )
        if phone_number or phone_entity:
            return {"transfer_type": "mobile_money"}

        # Verifier le texte pour des mots-cles
        text = tracker.latest_message.get("text", "").lower()
        if any(kw in text for kw in ["neero", "wallet"]):
            return {"transfer_type": "neero"}
        if any(kw in text for kw in ["mobile", "momo", "orange", "mtn"]):
            return {"transfer_type": "mobile_money"}

        return {"transfer_type": None}

    def _normalize_transfer_type(self, value: str) -> Optional[str]:
        """Normalise les valeurs de transfer_type vers 'neero' ou 'mobile_money'."""
        if not value:
            return None

        value_lower = value.lower().strip()

        neero_keywords = ["neero", "wallet", "wallet neero"]
        mobile_keywords = ["mobile money", "mobile", "momo", "orange money",
                          "mtn momo", "mtn", "orange", "om"]

        if any(kw in value_lower for kw in neero_keywords):
            return "neero"
        if any(kw in value_lower for kw in mobile_keywords):
            return "mobile_money"

        return None

    def validate_transfer_type(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valide le slot transfer_type."""

        if slot_value in ["neero", "mobile_money"]:
            return {"transfer_type": slot_value}

        # Essayer de normaliser
        normalized = self._normalize_transfer_type(slot_value)
        if normalized:
            return {"transfer_type": normalized}

        dispatcher.utter_message(
            text="Type de transfert non reconnu. Veuillez choisir Neero ou Mobile Money."
        )
        return {"transfer_type": None}

    def validate_amount(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valide le slot amount."""

        if not slot_value:
            return {"amount": None}

        try:
            # Gerer les montants en string
            amount_str = str(slot_value).replace(" ", "").replace(",", "")
            amount = int(amount_str)

            if amount <= 0:
                dispatcher.utter_message(
                    text="Le montant doit etre superieur a 0."
                )
                return {"amount": None}

            if amount > 10000000:  # Limite 10 millions
                dispatcher.utter_message(
                    text="Le montant maximum autorise est de 10 000 000 FCFA."
                )
                return {"amount": None}

            return {"amount": str(amount)}

        except ValueError:
            dispatcher.utter_message(
                text="Veuillez entrer un montant valide en chiffres."
            )
            return {"amount": None}

    def validate_neero_id(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valide le slot neero_id (doit commencer par @)."""

        if not slot_value:
            return {"neero_id": None}

        # S'assurer qu'il commence par @
        if not slot_value.startswith("@"):
            slot_value = f"@{slot_value}"

        # Validation: @ suivi de 3-20 caracteres alphanumeriques/underscore
        if re.match(r"^@[a-zA-Z0-9_]{3,20}$", slot_value):
            return {"neero_id": slot_value}

        dispatcher.utter_message(
            text="ID Neero invalide. Le format doit etre @username (3-20 caracteres alphanumeriques)."
        )
        return {"neero_id": None}

    def validate_phone_number(
        self,
        slot_value: Any,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: DomainDict,
    ) -> Dict[Text, Any]:
        """Valide le slot phone_number (format Cameroun)."""

        if not slot_value:
            return {"phone_number": None}

        # Retirer espaces et tirets
        phone = str(slot_value).replace(" ", "").replace("-", "")

        # Pattern Cameroun: optionnel +237, puis 6 suivi de 8 chiffres
        pattern = r"^(\+?237)?6[0-9]{8}$"

        if re.match(pattern, phone):
            # Normaliser a 9 chiffres (sans code pays)
            if phone.startswith("+237"):
                phone = phone[4:]
            elif phone.startswith("237"):
                phone = phone[3:]
            return {"phone_number": phone}

        dispatcher.utter_message(
            text="Numero de telephone invalide. Format attendu: 6XXXXXXXX"
        )
        return {"phone_number": None}


class ActionSubmitTransfer(Action):
    """Soumet le transfert apres completion du formulaire."""

    def name(self) -> Text:
        return "action_submit_transfer"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        transfer_type = tracker.get_slot("transfer_type")
        amount = tracker.get_slot("amount")

        if transfer_type == "neero":
            neero_id = tracker.get_slot("neero_id")
            dispatcher.utter_message(
                text=f"Vous souhaitez faire un transfert Neero de {amount} FCFA a l'utilisateur {neero_id}. Confirmez-vous ?",
                buttons=[
                    {"title": "Confirmer", "payload": "/affirm"},
                    {"title": "Annuler", "payload": "/deny"}
                ]
            )
        else:
            phone_number = tracker.get_slot("phone_number")
            dispatcher.utter_message(
                text=f"Vous souhaitez effectuer un transfert mobile money de {amount} FCFA au numero {phone_number}. Confirmez-vous ?",
                buttons=[
                    {"title": "Confirmer", "payload": "/affirm"},
                    {"title": "Annuler", "payload": "/deny"}
                ]
            )

        return []


class ActionClearTransactionSlots(Action):
    """Reinitialise les slots de transaction apres confirmation/annulation."""

    def name(self) -> Text:
        return "action_clear_transaction_slots"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        return [
            SlotSet("amount", None),
            SlotSet("phone_number", None),
            SlotSet("neero_id", None),
            SlotSet("currency", None),
            SlotSet("transfer_type", None),
        ]


class ActionRestart(Action):
    """Reinitialise completement la conversation (tous les slots + historique)."""

    def name(self) -> Text:
        return "action_restart"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        dispatcher.utter_message(text="Conversation reinitialisee. Comment puis-je vous aider ?")
        return [Restarted()]


class ActionGetUserInfo(Action):
    """Recupere les informations d'un utilisateur depuis l'API externe par son ID."""

    def name(self) -> Text:
        return "action_get_user_info"

    def _fetch_user_by_id(self, user_id: int) -> Optional[Dict]:
        """Recupere un utilisateur par son ID depuis l'API."""
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
