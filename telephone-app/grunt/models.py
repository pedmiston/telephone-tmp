from django.core.exceptions import ValidationError
from django.core.urlresolvers import reverse
from django.db import models

from .handlers import message_path

class Game(models.Model):
    """ Top-level control over calls

    Games can be played or inspected. If the game is being played, the
    game determines which chain the player should contribute to next.
    If the game is being inspected, the game returns all of the chains
    in the game.
    """
    # The name of the game. Visible to the players, but not used for
    # naming entries or chains. Instead, the int primary key (pk) is
    # used.
    name = models.CharField(blank = True, null = True, max_length = 30)

    possible_game_types = [('PUB', 'public'), ('MTK', 'mturk')]
    type = models.CharField(choices = possible_game_types, default = 'PUB',
            max_length = 3)

    # Completion codes are presented to MTurk players
    completion_code = models.CharField(blank = True, null = True,
            max_length = 20)

    # When playing a game, how should the next call be determined?
    chain_order_choices  = [('SEQ', 'sequential'), ('RND', 'random')]
    chain_order = models.CharField(choices = chain_order_choices,
            default = 'SEQ', max_length = 3)

    # Active games are visible
    status_choices = [('ACTIV', 'active'), ('INACT', 'inactive')]
    status = models.CharField(choices = status_choices, default = 'ACTIV',
                              max_length = 5)

    def get_play_url(self):
        """ URL for playing this game """
        return reverse('play', kwargs = {'pk': self.pk})

    def get_inspect_url(self):
        """ URL for inspecting this game """
        return reverse('inspect', kwargs = {'pk': self.pk})

    def get_absolute_url(self):
        """ By default, games are played when viewed """
        return self.get_play_url()

    def pick_next_chain(self, receipts = list()):
        """ Determine which chain should be played next

        Fails when:
        (a) there are no chains in the game
        (b) there are no chains not in receipts

        Parameters
        ----------
        receipts: list of chains already made, by primary key

        Returns
        -------
        a Chain object, determined by chain order
        """
        chains = self.chain_set.all()
        if chains.count() == 0:
            raise Chain.DoesNotExist('No chains in game')

        remaining_chains = chains.exclude(pk__in = receipts)
        if not remaining_chains:
            raise Chain.DoesNotExist('All receipts present')

        if self.chain_order == 'RND':
            remaining_chains = remaining_chains.order_by('?')

        return remaining_chains[0]

    def dirname(self):
        """ The name of the directory to hold all of this game's messages """
        return 'game-{pk}'.format(pk = self.pk)

    def __str__(self):
        """ If the game was not created with a name, provide the directory """
        return self.name or self.dirname()

class Chain(models.Model):
    """ A collection of messages """
    game = models.ForeignKey(Game)
    message_selection_choices = [('YNG', 'youngest'), ('RND', 'random')]
    selection_method = models.CharField(choices = message_selection_choices,
            max_length = 3, default = 'YNG')

    def pick_next_message(self):
        """ Determine which message should be viewed next

        Fails when there are no messages available.

        Returns
        -------
        a Message object
        """
        messages = self.message_set.filter(audio = '')
        if messages.count() == 0:
            raise Message.DoesNotExist('No available messages')

        if self.selection_method == 'RND':
            messages = messages.order_by('?')
        else:
            messages = sorted(list(messages), key = lambda msg: msg.generation)

        return messages[0]

    def to_dict(self):
        """ Serialize this chain and it's messages """
        chain_dict = {}
        chain_dict['pk'] = self.pk
        chain_dict['messages'] = [m.to_dict() for m in self.message_set.all()]
        return chain_dict

    def dirname(self):
        """ The name of the directory to hold all of this chain's messages """
        return 'chain-{pk}'.format(pk = self.pk)

    def dirpath(self):
        """ The path to this chain's directory, relative to MEDIA_ROOT """
        path_kwargs = {
            'game_dir': self.game.dirname(),
            'chain_dir': self.dirname()
        }
        return '{game_dir}/{chain_dir}'.format(**path_kwargs)

class Message(models.Model):
    """ Audio recordings """
    chain = models.ForeignKey(Chain)
    name = models.CharField(blank = True, max_length = 30)
    parent = models.ForeignKey('self', blank = True, null = True)
    generation = models.IntegerField(default = 0, editable = False)
    audio = models.FileField(upload_to = message_path, blank = True)

    def full_clean(self, *args, **kwargs):
        if self.parent:
            self.generation = self.parent.generation + 1
        super(Message, self).full_clean(*args, **kwargs)

    def to_dict(self):
        message_dict = {}
        message_dict['pk'] = self.pk
        message_dict['generation'] = self.generation
        message_dict['audio'] = self.audio.url if self.audio else None
        message_dict['parent'] = self.parent.id if self.parent else None

        # add post URLs to the objects
        message_dict['sprout_url'] = reverse('sprout', kwargs = {'pk': self.pk})
        if not self.audio:
            message_dict['close_url'] = reverse('close', kwargs = {'pk': self.pk})

            message_dict['upload_url'] = reverse('upload', kwargs = {'pk': self.pk})

        return message_dict

    def get_absolute_url(self):
        return reverse('inspect', kwargs = {'pk': self.chain.game.pk})

    def __str__(self):
        if self.name:
            return self.name
        else:
            return 'message-{pk}'.format(pk = self.pk)

    def replicate(self):
        child = Message(chain = self.chain, parent = self)
        child.full_clean()
        child.save()
        return child

    def save(self, *args, **kwargs):
        return super(Message, self).save(*args, **kwargs)
