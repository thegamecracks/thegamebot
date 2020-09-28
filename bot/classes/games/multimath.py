import asyncio
import collections
import math
import operator
import random

import discord

from bot.classes.get_reaction import get_reaction

Operator = collections.namedtuple('Operator', ['symbol', 'func'])

OPERATORS = (
    Operator('+', operator.add),
    Operator('-', operator.sub),
    Operator('*', operator.mul),
    Operator('/', operator.truediv)
)


class MultimathGame:

    precision = 2

    def __init__(
            self, *,
            color=0x000000):
        self.a = 0
        self.b = 0
        self.op = None
        self.ans = 0

        self.question_count = 0

        self.color = color

    def answer_question(self, user_answer):
        """
        Returns:
            Tuple[bool, str]: A boolean indicating whether the answer
                was correct, along with a message to edit the embed
                with.
        """
        user_answer = round(user_answer, self.precision)
        if user_answer == self.ans:
            return True, 'Correct!'
        return False, (f'{user_answer:g} was incorrect; '
                       f'the answer was {self.ans:g}!')

    def embed_begin(self, user: discord.User):
        "Return an Embed to be used as the beginning of the game."
        return discord.Embed(
            title=f'Multimath started for {user.name}',
            description='React to the emojis to answer the question!',
            color=self.color
        )

    def embed_finish(self, user: discord.User):
        score = self.question_count - 1
        return discord.Embed(
            title=f'Multimath finished by {user.name}',
            description=f'Final score: {score:,}',
            color=self.color
        )

    def embed_question(self, answers: dict, time_to_answer):
        description = (f'Time to answer: {time_to_answer:,g}s\n'
                       f'What is {self.a} {self.op.symbol} {self.b}?\n')
        description += '\n'.join(
            f'{emoji}: {ans:g}' for emoji, ans in answers.items())

        return discord.Embed(
            title=f'Question {self.question_count:,}',
            description=description,
            color=self.color
        )

    def generate_values(self):
        self.question_count += 1
        self.a = random.randint(1, 10)
        self.b = random.randint(1, 10)
        self.op = random.choice(OPERATORS)
        self.ans = round(self.op.func(self.a, self.b), self.precision)
        if self.ans == int(self.ans):
            # no decimal, turn to integer
            self.ans = int(self.ans)

        return self.a, self.b, self.op, self.ans

    def generate_false_answers(self, amount: int = 1, deviation: int = 20):
        "Generate numbers close to self.ans."
        is_decimal = isinstance(self.ans, float)
        rounder = 10 ** self.precision

        if is_decimal and self.op.symbol == '/':
            # Decimal answer from division; make small lower/upper bounds
            # so answers are harder to figure out
            deviation = 1
            middle = random.random()
        else:
            middle = random.randint(0, deviation)
        lower, upper = self.ans - middle, self.ans + deviation - middle
        # Generate `amount + 1` non-colliding answers so if it generates
        # the answer, it can be ignored in the loop, and otherwise the extra
        # number can be thrown away
        answers = [
            n / rounder
            for n in random.sample(
                range(
                    round(math.copysign(lower * rounder, self.ans))
                    if is_decimal else round(lower * rounder),
                    round(math.copysign(upper * rounder, self.ans))
                    if is_decimal else round(upper * rounder),
                ), amount + 1
            ) if n != self.ans * rounder
        ]
        if len(answers) > amount:
            # Extra generated number
            del answers[-1]

        if not is_decimal:
            # Max amount of potential integers
            integers = amount // 2
            # 50% chance to round number to integer
            for i, n in enumerate(answers):
                if not integers:
                    break
                elif random.randint(0, 1) and round(n) not in answers:
                    answers[i] = round(n)
                    integers -= 1

        return answers


class BotMultimathGame:
    def __init__(self, ctx, options=['🇦', '🇧', '🇨', '🇩', '🇪']):
        self._ctx = ctx
        self._client = ctx.bot
        self.options = options

        self.game = MultimathGame(color=0xFF8002)

    async def run(self, *, channel=None, users=None):
        """
        Args:
            channel (Optional[discord.TextChannel]):
                The channel to send the message to.
                If None, uses the channel in self._ctx.
            users (Optional[Union[True, List[discord.User]]]):
                A list of users that can participate in the game.
                If None, the author of self._ctx will be the only participant.
                If True, anyone can participate.
        """
        async def finish_and_show_score(header, last_answerer=None):
            if last_answerer is None:
                last_answerer = self._ctx.author
            embed_finish = self.game.embed_finish(last_answerer)
            embed_finish.description = '\n'.join(
                [header, embed_finish.description])
            await message.edit(embed=embed_finish)

        if users is None:
            # Allow only caller
            users = [self._ctx.author]
        elif users is True:
            # Allow all participants
            users = None
        if channel is None:
            # Assumes game to be started in the caller's channel
            channel = self._ctx.channel

        message = await channel.send(
            embed=self.game.embed_begin(self._ctx.author)
        )

        for emoji in self.options:
            await message.add_reaction(emoji)

        time_to_answer = 10
        time_intermission = 3
        reaction = user = None

        await asyncio.sleep(2)

        # Begin playing
        while True:
            # Generate question
            self.game.generate_values()
            answers = self.game.generate_false_answers(
                len(self.options) - 1)
            answers.append(self.game.ans)
            random.shuffle(answers)
            answers_dict = {
                emoji: answer for emoji, answer in zip(self.options, answers)}

            # Ask question
            embed_question = self.game.embed_question(
                answers_dict, time_to_answer)
            await message.edit(embed=embed_question)

            is_correct = False
            try:
                reaction, user = await get_reaction(
                    self._client, message,
                    self.options, users,
                    timeout=time_to_answer
                )
            except asyncio.TimeoutError:
                # Timed out!
                response = f'Too late! {time_to_answer:,g} seconds have passed!'
                await message.edit(embed=discord.Embed(
                    title=embed_question.title,
                    description=response,
                    color=self.game.color
                ))
            else:
                # Get response
                user_answer = answers_dict[reaction.emoji]
                is_correct, response = self.game.answer_question(user_answer)

                # Respond with answer
                embed_answer = discord.Embed(
                    title=embed_question.title,
                    description=response,
                    color=self.game.color
                )
                await message.edit(embed=embed_answer)

            await asyncio.sleep(time_intermission)

            if is_correct:
                # Reduce time to answer
                # NOTE: keep time_to_answer rounded to 2 places so it
                # displays nicely
                time_to_answer = round(max(3, time_to_answer - 1), 2)
                time_intermission = max(1, time_intermission - 0.15)
            else:
                response = 'Expression: {} {} {}\n{}'.format(
                    self.game.a,
                    self.game.op.symbol,
                    self.game.b,
                    response
                )
                await finish_and_show_score(response, user)
                return
