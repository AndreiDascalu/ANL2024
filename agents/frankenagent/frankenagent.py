import logging
import random
from random import randint
from time import time
from typing import cast
from decimal import Decimal
from geniusweb.actions.Accept import Accept
from geniusweb.actions.Action import Action
from geniusweb.actions.Offer import Offer
from geniusweb.actions.PartyId import PartyId
from geniusweb.bidspace.AllBidsList import AllBidsList
from geniusweb.inform.ActionDone import ActionDone
from geniusweb.inform.Finished import Finished
from geniusweb.inform.Inform import Inform
from geniusweb.inform.Settings import Settings
from geniusweb.inform.YourTurn import YourTurn
from geniusweb.issuevalue.Bid import Bid
from geniusweb.issuevalue.Domain import Domain
from geniusweb.party.Capabilities import Capabilities
from geniusweb.party.DefaultParty import DefaultParty
from geniusweb.profile.utilityspace.LinearAdditiveUtilitySpace import (
    LinearAdditiveUtilitySpace,
)
from geniusweb.profileconnection.ProfileConnectionFactory import (
    ProfileConnectionFactory,
)
from geniusweb.progress.ProgressTime import ProgressTime
from geniusweb.references.Parameters import Parameters
from tudelft_utilities_logging.ReportToLogger import ReportToLogger

from .utils.opponent_model import OpponentModel


class FrankenAgent(DefaultParty):
    """
    Template of a Python geniusweb agent.
    """

    def __init__(self):
        super().__init__()
        self.getReporter().log(logging.INFO, "party is initialized")

        self.domain: Domain = None
        self.parameters: Parameters = None
        self.profile: LinearAdditiveUtilitySpace = None
        self.progress: ProgressTime = None
        self.me: PartyId = None
        self.other: str = None
        self.settings: Settings = None
        self.storage_dir: str = None

        self.last_received_bid: Bid = None
        self.opponent_model: OpponentModel = None

    def notifyChange(self, data: Inform):
        """MUST BE IMPLEMENTED
        This is the entry point of all interaction with your agent after is has been initialised.
        How to handle the received data is based on its class type.

        Args:
            info (Inform): Contains either a request for action or information.
        """

        # a Settings message is the first message that will be send to your
        # agent containing all the information about the negotiation session.
        if isinstance(data, Settings):
            self.settings = cast(Settings, data)
            self.me = self.settings.getID()

            # progress towards the deadline has to be tracked manually through the use of the Progress object
            self.progress = self.settings.getProgress()

            self.parameters = self.settings.getParameters()
            self.storage_dir = self.parameters.get("storage_dir")

            # the profile contains the preferences of the agent over the domain
            profile_connection = ProfileConnectionFactory.create(
                data.getProfile().getURI(), self.getReporter()
            )
            self.profile = profile_connection.getProfile()
            self.domain = self.profile.getDomain()
            profile_connection.close()

        # ActionDone informs you of an action (an offer or an accept)
        # that is performed by one of the agents (including yourself).
        elif isinstance(data, ActionDone):
            action = cast(ActionDone, data).getAction()
            actor = action.getActor()

            # ignore action if it is our action
            if actor != self.me:
                # obtain the name of the opponent, cutting of the position ID.
                self.other = str(actor).rsplit("_", 1)[0]

                # process action done by opponent
                self.opponent_action(action)
        # YourTurn notifies you that it is your turn to act
        elif isinstance(data, YourTurn):
            # execute a turn
            self.my_turn()

        # Finished will be send if the negotiation has ended (through agreement or deadline)
        elif isinstance(data, Finished):
            self.save_data()
            # terminate the agent MUST BE CALLED
            self.logger.log(logging.INFO, "party is terminating:")
            super().terminate()
        else:
            self.logger.log(logging.WARNING, "Ignoring unknown info " + str(data))

    def getCapabilities(self) -> Capabilities:
        """MUST BE IMPLEMENTED
        Method to indicate to the protocol what the capabilities of this agent are.
        Leave it as is for the ANL 2022 competition

        Returns:
            Capabilities: Capabilities representation class
        """
        return Capabilities(
            set(["SAOP"]),
            set(["geniusweb.profile.utilityspace.LinearAdditive"]),
        )

    def send_action(self, action: Action):
        """Sends an action to the opponent(s)

        Args:
            action (Action): action of this agent
        """
        print("Sent action")
        self.getConnection().send(action)

    # give a description of your agent
    def getDescription(self) -> str:
        """MUST BE IMPLEMENTED
        Returns a description of your agent. 1 or 2 sentences.

        Returns:
            str: Agent description
        """
        return "FrankenAgent implementation for the Collaborative AI course"

    def opponent_action(self, action):
        """Process an action that was received from the opponent.

        Args:
            action (Action): action of opponent
        """
        # if it is an offer, set the last received bid
        print("Opponent action")
        if isinstance(action, Offer):
            # create opponent model if it was not yet initialised
            if self.opponent_model is None:
                self.opponent_model = OpponentModel(self.domain)

            bid = cast(Offer, action).getBid()

            # update opponent model with bid
            self.opponent_model.update(bid)
            # set bid as last received
            self.last_received_bid = bid

    # NOTE Modified
    def my_turn(self):
        """This method is called when it is our turn. It should decide upon an action
        to perform and send this action to the opponent.
        """
        # check if the last received offer is good enough based on
        # my upcoming bid and the last received bid from opp
        bid = self.find_bid()

        action = Offer(self.me, bid)
        print("Offered a bid" + str(bid))
        if self.accept(bid, self.last_received_bid):
            # if so, accept the offer
            action = Accept(self.me, self.last_received_bid)
            print("I accepted it!!!")
            print(self.last_received_bid)

        self.send_action(action)

    def save_data(self):
        """This method is called after the negotiation is finished. It can be used to store data
        for learning capabilities. Note that no extensive calculations can be done within this method.
        Taking too much time might result in your agent being killed, so use it for storage only.
        """
        data = "Data for learning (see README.md)"
        with open(f"{self.storage_dir}/data.md", "w") as f:
            f.write(data)

    ###########################################################################################
    ################################## Example methods below ##################################
    ###########################################################################################

    # Combination of acceptance strategy (AC_Combi)
    # Makes use of an AC_next acceptance strategy, and AC_time acceptance strategy
    # AC_const performs worst of all AC, so no point in using it
    # NOTE Modified
    def accept(self, my_upcoming_bid: Bid, opponent_offer: Bid, T=0.95) -> bool:
        if opponent_offer is None:
            return False

        progress = self.progress.get(time() * 1000)

        # Create accept conditions, either AC_next or AC_time has to be satisfied
        accept_condition = self.profile.getUtility(
            opponent_offer
        ) > self.profile.getUtility(my_upcoming_bid) or (progress > T)

        return accept_condition

    def find_bid(self) -> Bid:
        # compose a list of all possible bids
        # domain = self.profile.getDomain()
        # all_bids = AllBidsList(domain)

        # best_bid_score = 0.0
        # best_bid = None

        # # take 500 attempts to find a bid according to a heuristic score
        # for _ in range(500):
        #     bid = all_bids.get(randint(0, all_bids.size() - 1))
        #     bid_score = self.score_bid(bid)
        #     if bid_score > best_bid_score:
        #         best_bid_score, best_bid = bid_score, bid
        # return best_bid
        # Get the utility of the agent's previous offer
        previous_offer_utility = self.profile.getUtility(self.last_received_bid)

        # Compose a list of all possible bids
        domain = self.profile.getDomain()
        all_bids = AllBidsList(domain)

        # Determine the number of bids available
        num_bids = all_bids.size()

        # Randomly select a subset of indices from the entire set of bids
        max_bids_to_check = 500
        random_indices = random.sample(
            range(num_bids), min(num_bids, max_bids_to_check)
        )

        # Initialize a list to store similar bids with concession
        similar_bids_with_concession = []

        # Iterate through randomly selected indices and retrieve the corresponding bids
        for index in random_indices:
            bid = all_bids.get(index)
            bid_utility = self.profile.getUtility(bid)

            # Check if the bid has similar utility with a minimal concession
            if bid_utility > previous_offer_utility - Decimal(0.9):
                similar_bids_with_concession.append(bid)

        # If no bids with similar utility, choose randomly from all possible bids
        if not similar_bids_with_concession:
            return random.choice(all_bids)

        # Choose randomly from similar bids with concession
        return random.choice(similar_bids_with_concession)

    def score_bid(self, bid: Bid, alpha: float = 0.95, eps: float = 0.1) -> float:
        """Calculate heuristic score for a bid

        Args:
            bid (Bid): Bid to score
            alpha (float, optional): Trade-off factor between self interested and
                altruistic behaviour. Defaults to 0.95.
            eps (float, optional): Time pressure factor, balances between conceding
                and Boulware behaviour over time. Defaults to 0.1.

        Returns:
            float: score
        """
        progress = self.progress.get(time() * 1000)

        our_utility = float(self.profile.getUtility(bid))

        time_pressure = 1.0 - progress ** (1 / eps)
        score = alpha * time_pressure * our_utility

        if self.opponent_model is not None:
            opponent_utility = self.opponent_model.get_predicted_utility(bid)
            opponent_score = (1.0 - alpha * time_pressure) * opponent_utility
            score += opponent_score

        return score
