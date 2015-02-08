import shutil
import subprocess
import tempfile

from django.conf import settings
from django.core.files import File
from django.core.files.storage import FileSystemStorage
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from unipath import Path
from unittest import skip
from model_mommy import mommy

import grunt.models
from grunt.models import Game, Seed, Cluster, Chain, Entry

class ModelTests(TestCase):

    def setUp(self):
        """
        I think this storage manipulation might be all bullshit because the
        way things are set up now everything must be servable immediately so
        everything needs to be in the media root in order to do anything at
        all.
        """
        self.temp_dir = tempfile.mkdtemp()
        self._orig_storage = grunt.models.storage
        grunt.models.storage = FileSystemStorage(self.temp_dir)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)
        grunt.models.storage = self._orig_storage


class GameTests(ModelTests):

    def test_make_a_game(self):
        """ Make a game """
        game = Game()
        game.full_clean()
        game.save()

    def test_game_options(self):
        """ Games select clusters in order by default """
        game = Game()
        game.full_clean()
        self.assertEquals(game.order, 'SEQ')

        # orders can be selected at random too
        game = Game(order = 'RND')
        game.full_clean()  # should not raise

    def test_game_str(self):
        """ By default games are named based on their primary key """
        game = Game.objects.create()
        self.assertEquals(str(game), 'game-{}'.format(game.pk))

        # But names can be provided
        name_game = Game.objects.create(name = 'The Name')
        self.assertEquals(str(name_game), 'The Name')

    def test_game_dir(self):
        """ Game data are stored relative to MEDIA_ROOT """
        game = Game()
        game.full_clean()
        game.save()
        self.assertEquals(game.dir(), 'game-{pk}'.format(pk = game.pk))

        name_game = Game(name = 'The Name')
        name_game.full_clean()
        name_game.save()
        self.assertEquals(name_game.dir(), 'game-{}'.format(name_game.pk))

class SeedTests(ModelTests):

    def setUp(self):
        super(SeedTests, self).setUp()
        filepath = Path(settings.TEST_MEDIA_DIR, 'test-audio.wav')
        self.content = File(open(filepath, 'rb'))

    def test_make_a_seed(self):
        """ Make a seed """
        seed = Seed(name = 'seed', content = self.content)
        seed.full_clean()
        seed.save()

    def test_seed_requirements(self):
        """ A name w/o a file, or a file w/o a name raises an error """
        valid_name = 'seed'
        valid_content = self.content

        no_name = Seed(content = valid_content)
        with self.assertRaises(ValidationError):
            no_name.full_clean()

        no_content = Seed(name = valid_name)
        with self.assertRaises(ValidationError):
            no_content.full_clean()

        valid = Seed(name = valid_name, content = valid_content)
        valid.full_clean()  # should not raise

    def test_seed_str(self):
        """ Seeds are named """
        seed = Seed.objects.create(name = 'seed', content = self.content)
        self.assertEquals(str(seed), 'seed')

    def test_seed_names_are_unique(self):
        """ Seeds can't have the same name """
        repeated = 'repeated-name'

        first = Seed(name = repeated, content = self.content)
        first.full_clean()
        first.save()

        second = Seed(name = repeated, content = self.content)
        with self.assertRaises(ValidationError):
            second.full_clean()

        third = Seed(name = "new-name", content = self.content)
        third.full_clean()  # should not raise
        third.save()

    def test_seeds_are_saved_to_correct_directory(self):
        """ Seeds are saved to their own directory """
        seed = Seed(name = 'seed', content = self.content)
        seed.save()
        self.assertRegexpMatches(seed.content.url, r'/seeds/')

    def test_seed_files_are_saved_as_wav(self):
        """ In the grunt app all seeds are .wav files """
        seed = Seed(name = 'seed', content = self.content)
        seed.save()
        seed_content_url = Path(seed.content.url)
        self.assertEquals(seed_content_url.ext, '.wav')

class ClusterTests(ModelTests):

    def setUp(self):
        super(ClusterTests, self).setUp()
        self.game = mommy.make(Game)
        self.seed = mommy.make(Seed)

    def test_make_a_cluster(self):
        """ Make a cluster """
        cluster = Cluster(
            game = self.game,
            seed = self.seed,
        )
        cluster.full_clean()
        cluster.save()

    def test_cluster_requirements(self):
        """ A game, a seed, and a receipt are all required for validation """
        empty_cluster = Cluster()
        try:
            empty_cluster.full_clean()
        except ValidationError as validation_error:
            errors = validation_error.error_dict
            self.assertListEqual(errors.keys(), ['game', 'seed'])

    def test_cluster_defaults(self):
        """ Clusters select the shortest chains by default """
        cluster = Cluster(
            game = self.game,
            seed = self.seed,
        )
        cluster.full_clean()
        self.assertEquals(cluster.method, 'SRT')

    def test_cluster_str(self):
        """ Clusters are named based on the name of the seed """
        cluster = Cluster.objects.create(
            game = self.game, seed = self.seed,
        )
        self.assertEquals(str(cluster), str(self.seed))

    def test_cluster_dir(self):
        cluster = Cluster.objects.create(
            game = self.game, seed = self.seed
        )
        self.assertEquals(cluster.dir(), str(self.seed))


class ChainTests(ModelTests):

    def setUp(self):
        super(ChainTests, self).setUp()
        self.cluster = mommy.make(Cluster)

    def test_make_a_chain(self):
        """ Make a chain """
        chain = Chain(cluster = self.cluster)
        chain.full_clean()
        chain.save()

    def test_chain_requirements(self):
        """ Validating a chain without a cluster raises an error """
        no_cluster = Chain()
        with self.assertRaises(ValidationError):
            no_cluster.full_clean()

    def test_chain_str(self):
        """ Chains are named based on their number within the cluster """
        cluster_1, cluster_2 = mommy.make(Cluster, _quantity = 2)

        mommy.make(Chain, cluster = cluster_1, _quantity = 3)
        mommy.make(Chain, cluster = cluster_2, _quantity = 3)

        cluster_1_chains = cluster_1.chain_set.all()
        self.assertListEqual(map(str, cluster_1_chains), ['0', '1', '2'])

        cluster_2_chains = cluster_2.chain_set.all()
        self.assertListEqual(map(str, cluster_2_chains), ['0', '1', '2'])

    def test_chain_directory(self):
        """ Chains know the directory in which to save entries """
        chain = Chain.objects.create(cluster = self.cluster)
        expected_dir = '{game}/{cluster}/{chain}/'.format(
            game = self.cluster.game.dir(),
            cluster = self.cluster.dir(),
            chain = chain
        )
        self.assertEquals(chain.dir(), expected_dir)

    def test_preparing_next_entry(self):
        """ Chains prepare the next entry using the last entry as parent """
        chain = Chain.objects.create(cluster = self.cluster)
        entry = mommy.make(Entry, chain = chain)

        next_entry = chain.prepare_entry()

        self.assertEquals(next_entry.chain.pk, chain.pk)
        self.assertEquals(next_entry.parent.pk, entry.pk)

    def test_requirements_for_preparing_next_entry(self):
        """ Chains need a seed entry in order to prepare the next one """
        empty_chain = Chain.objects.create(cluster = self.cluster)
        with self.assertRaises(Entry.DoesNotExist):
            empty_chain.prepare_entry()

    def test_create_entry_from_seed(self):
        """ Empty chains can create an entry from the seed """
        chain = mommy.make(Chain, cluster = self.cluster)
        entry = chain.create_entry_from_seed()
        self.assertEquals(chain.entry_set.count(), 1)

        # chain has to be empty to create an entry from the seed
        with self.assertRaises(ValidationError):
            chain.create_entry_from_seed()

        self.assertEquals(chain.entry_set.count(), 1)

    def test_create_with_entry(self):
        """ ChainManager can make a chain with an entry """
        chain = self.cluster.chain_set.create_with_entry()
        self.assertEquals(chain.entry_set.count(), 1)

    def test_create_multiple(self):
        """ ChainManager can make multiple chains at once """
        self.cluster.chain_set.create_multiple(_quantity = 5)
        self.assertEquals(self.cluster.chain_set.count(), 5)

    def test_create_multiple_with_entry(self):
        """ ChainManager can make multiple chains all with an entry """
        chains = self.cluster.chain_set.create_multiple(
            _quantity = 10, _with_entry = True
        )
        self.assertEquals(len(chains), 10)
        for chain in chains:
            self.assertEquals(chain.entry_set.count(), 1)


class EntryTests(ModelTests):

    def setUp(self):
        super(EntryTests, self).setUp()
        self.chain = mommy.make(Chain)
        mommy.make(Entry, chain = self.chain)

        test_file = Path(settings.TEST_MEDIA_DIR, 'test-audio.wav')
        self.content = File(open(test_file, 'rb'))

    def make_entry(self, save = True):
        entry = Entry(
            content = self.content,
            chain = self.chain,
            parent = self.chain.entry_set.last()
        )
        entry.full_clean()
        if save:
            entry.save()
        return entry

    def test_make_an_entry(self):
        """ Make an entry """
        parent = self.chain.entry_set.last()
        entry = Entry(
            content = self.content,
            chain = self.chain,
            parent = parent
        )
        entry.full_clean()
        entry.save()

    def test_entry_requirements(self):
        """ First generation entries require content and a chain """
        empty_chain = mommy.make(Chain)
        no_content = Entry(chain = empty_chain)
        with self.assertRaises(ValidationError):
            no_content.full_clean()

        no_chain = Entry(content = self.content)
        with self.assertRaises(ValidationError):
            no_chain.full_clean()

        valid = Entry(chain = empty_chain, content = self.content)
        valid.full_clean()  # should not raise

    def test_entries_require_a_parent(self):
        """ Second+ generation entries also require a parent """
        self.assertGreater(self.chain.entry_set.count(), 0)
        entry = Entry(content = self.content, chain = self.chain)
        with self.assertRaises(ValidationError):
            entry.full_clean()

    def test_entry_defaults(self):
        """ Default generation is 0 """
        entry = Entry.objects.create(content=self.content, chain=self.chain)
        self.assertEquals(entry.generation, 0)

    def test_generation_is_filled_on_clean(self):
        """ Generation is parent.generation + 1 """
        parent = self.chain.entry_set.last()
        entry = self.make_entry(save = False)
        self.assertEquals(entry.generation, parent.generation + 1)

    def test_entry_str(self):
        """ Entries are named by the seed and the generation """
        expected_name = '{seed}-{generation}'.format(
            seed = str(self.chain.cluster.seed),
            generation = 1
        )

        entry = self.make_entry(save = False)
        self.assertEquals(str(entry), expected_name)

    def test_entries_are_saved_to_chain_directory(self):
        """ Entries should be saved in the chain directory """
        entry = self.make_entry(save = True)
        self.assertRegexpMatches(entry.content.url, self.chain.dir())

    def test_entry_files_are_saved_as_wav(self):
        """ In the grunt app all entries are .wav files """
        entry = self.make_entry(save = True)

        entry_content_url = Path(entry.content.url)
        self.assertEquals(entry_content_url.ext, '.wav')

    def test_entry_files_are_saved_with_interpretable_names(self):
        """ """
        expected_stem = '{seed}-{generation}'.format(
            seed = str(self.chain.cluster.seed),
            generation = 1
        )
        entry = self.make_entry(save = True)
        entry_content_url = Path(entry.content.url)
        self.assertEquals(entry_content_url.stem, expected_stem)

class GameNavigationTests(ModelTests):

    def setUp(self):
        super(GameNavigationTests, self).setUp()
        clusters_per = 5
        chains_per = 10

        # Populate a game with a number of Clusters
        self.game = mommy.make(Game)
        self.clusters = mommy.make(Cluster, game = self.game,
            _quantity = clusters_per)

        for cluster in self.clusters:
            mommy.make(Chain, cluster = cluster, _quantity = chains_per)

        self.visits = [cluster.pk for cluster in self.clusters]


    def test_pick_cluster(self):
        """ Game objects have a method that returns a related cluster """
        cluster = self.game.pick_cluster()
        self.assertIn(cluster, self.clusters)

    def test_pick_cluster_excluding_receipts(self):
        """ When picking the next cluster, exclude based on receipts """
        all_but_one = self.visits[:-1]
        next_cluster = self.game.pick_cluster(all_but_one)
        expected = Cluster.objects.get(pk = self.visits[-1])
        self.assertEquals(next_cluster, expected)

    def test_pick_clusters_in_order(self):
        """ Sequential games pick clusters in the order they were added """
        ordered_game = mommy.make(Game, order = 'SEQ')
        ordered_clusters = mommy.make(Cluster, game=ordered_game, _quantity=20)

        first = ordered_game.pick_cluster()
        second = ordered_game.pick_cluster([first.pk, ])

        self.assertEquals(first, ordered_clusters[0])
        self.assertEquals(second, ordered_clusters[1])

    def test_pick_clusters_at_random(self):
        """ Random games pick clusters at random

        * HACK! *
        """
        random_game = mommy.make(Game, order = 'RND')
        mommy.make(Cluster, game = random_game, _quantity = 20)

        first = random_game.pick_cluster()
        second = random_game.pick_cluster()
        third = random_game.pick_cluster()
        fourth = random_game.pick_cluster()

        self.assertFalse(first == second == third == fourth,
            "Clusters weren't picked at random (could be due to chance!)")

    def test_no_clusters_left(self):
        """ Simulate a user reaching the end of the game """
        with self.assertRaises(Cluster.DoesNotExist):
            self.game.pick_cluster(self.visits)


class ClusterNavigationTests(ModelTests):
    """ When a player reaches a cluster only one chain should be viewed """

    def setUp(self):
        super(ClusterNavigationTests, self).setUp()
        self.cluster = mommy.make(Cluster)
        self.chains = mommy.make(Chain, cluster = self.cluster, _quantity = 20)

    def test_cluster_can_pick_chain(self):
        """ Clusters have a method to select a related chain object """
        next_chain = self.cluster.pick_chain()
        self.assertIn(next_chain, self.chains)

    def test_cluster_can_pick_shortest_chain(self):
        """ By default clusters pick the shortest chain """
        cluster = mommy.make(Cluster, method = 'SRT')
        long_chain = mommy.make(Chain, cluster = cluster)
        mommy.make(Entry, chain = long_chain, _quantity = 2)

        short_chain = mommy.make(Chain, cluster = cluster)
        mommy.make(Entry, chain = short_chain)

        picked = cluster.pick_chain()
        self.assertEquals(picked, short_chain)

    def test_cluster_can_pick_chains_at_random(self):
        """ Clusters pick a chain at random """
        cluster = mommy.make(Cluster, method = 'RND')
        mommy.make(Chain, cluster = cluster, _quantity = 20)

        first = cluster.pick_chain()
        second = cluster.pick_chain()
        third = cluster.pick_chain()
        fourth = cluster.pick_chain()

        self.assertFalse(first == second == third == fourth,
            "Chains weren't picked at random (could be due to chance!)")

    def test_cluster_cant_pick_a_chain_if_none_exist(self):
        """ Edge case: trying to pick a chain without any in the cluster """
        new_cluster = mommy.make(Cluster)
        with self.assertRaises(Chain.DoesNotExist):
            new_cluster.pick_chain()

class GameShortcutTests(ModelTests):

    def test_games_can_prepare_entry(self):
        """ Traverse the game:cluster:chain.prepare_entry """
        game = mommy.make(Game)
        cluster = mommy.make(Cluster, game = game)
        chain = mommy.make(Chain, cluster = cluster)
        entry = mommy.make(Entry, chain = chain)
        prepared_by_game = game.prepare_entry()
        prepared_by_chain = chain.prepare_entry()
        self.assertEquals(prepared_by_game.parent, prepared_by_chain.parent)
        self.assertEquals(prepared_by_game.chain, prepared_by_chain.chain)