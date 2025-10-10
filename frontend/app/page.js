// frontend/app/page.js
'use client';

import { useEffect, useState } from 'react';

// --- Reusable Components (Tweaked for the new, spacious layout) ---
const Card = ({ suit, rank, faceDown = false }) => {
  if (faceDown)
    return (
      <div className="w-16 h-24 bg-red-800 rounded-lg border-2 border-red-900 shadow-inner"></div>
    );
  const suitSymbolMap = { s: '♠', h: '♥', d: '♦', c: '♣' };
  const suitColorMap = { s: 'text-gray-900', h: 'text-red-500', d: 'text-red-500', c: 'text-gray-900' };
  const displayRank = rank === 'T' ? '10' : rank;
  const displaySuit = suitSymbolMap[suit] || suit;
  const suitColor = suitColorMap[suit] || 'text-black';
  return (
    <div className="w-16 h-24 bg-white rounded-lg flex flex-col justify-between p-1 border border-gray-300 shadow-lg">
      <span className={`text-xl font-bold ${suitColor}`}>{displayRank}</span>
      <span className={`text-2xl self-center ${suitColor}`}>{displaySuit}</span>
      <span className={`text-xl font-bold self-end transform rotate-180 ${suitColor}`}>{displayRank}</span>
    </div>
  );
};

const PlayerInfo = ({ name, chips, cards = [], showCards = false, currentBet = 0, lastAction = null, isWinner = false }) => (
  <div
    className={`flex flex-col items-center p-6 rounded-xl w-full max-w-sm transition-all duration-500 ${
      isWinner ? 'bg-yellow-500/30 ring-2 ring-yellow-400' : 'bg-gray-800/70'
    }`}
  >
    <h2 className="text-2xl font-bold text-white">{name}</h2>
    <p className="text-xl text-yellow-400 font-mono mb-4">${chips}</p>
    <div className="flex space-x-3 h-24 items-center mb-4">
      {cards.length > 0 ? (
        cards.map((card, i) => <Card key={i} suit={card.suit} rank={card.rank} faceDown={!showCards} />)
      ) : (
        <>
          <div className="w-16 h-24 bg-gray-700/50 rounded-lg"></div>
          <div className="w-16 h-24 bg-gray-700/50 rounded-lg"></div>
        </>
      )}
    </div>
    <div className="h-10 flex items-center justify-center">
      {lastAction && <p className="text-lg font-semibold text-gray-300 animate-pulse">{lastAction}</p>}
    </div>
    {currentBet > 0 && (
      <div className="flex items-center space-x-2 bg-black/30 px-3 py-1 rounded-full">
        <div className="w-5 h-5 rounded-full bg-yellow-500"></div>
        <p className="text-white font-mono text-sm">${currentBet}</p>
      </div>
    )}
  </div>
);

// --- Main Page Component ---
export default function Home() {
  const [gameId, setGameId] = useState(null);
  const [gameState, setGameState] = useState(null);
  const [raiseAmount, setRaiseAmount] = useState(0);
  const [showPlayAgain, setShowPlayAgain] = useState(false);
  const API_URL = 'http://localhost:8000';

  const handleCreateGame = async (isNewGame = true) => {
    setShowPlayAgain(false);
    try {
      const url = isNewGame ? `${API_URL}/api/game` : `${API_URL}/api/game/next-hand`;

      const userPlayer = gameState?.players.find((p) => p.id === 'user');
      const botPlayer = gameState?.players.find((p) => p.id === 'bot');
      const requestBody = isNewGame
        ? null
        : JSON.stringify({
            user_chips: userPlayer?.chips || 10000,
            bot_chips: botPlayer?.chips || 10000,
            last_dealer_pos: gameState?.dealer_position || -1,
          });

      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: requestBody,
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      // THE FIX: Always update BOTH gameState and gameId from the new response
      setGameState(data);
      setGameId(data.game_id);
    } catch (error) {
      console.error('Failed to create/start next hand:', error);
    }
  };

  const handlePlayerAction = async (action, amount = 0) => {
    // THE FIX: Use gameState.game_id directly, as it's the single source of truth
    if (!gameState || !gameState.game_id) {
      console.error('Action attempted with no game ID.');
      return;
    }
    try {
      const response = await fetch(`${API_URL}/api/game/${gameState.game_id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, amount }),
      });
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }
      const data = await response.json();
      // THE FIX: Always update BOTH gameState and gameId from the new response
      setGameState(data);
      setGameId(data.game_id);
    } catch (error) {
      console.error(`Failed to perform action ${action}:`, error);
    }
  };

  useEffect(() => {
    if (gameState) {
      const minRaise = gameState.current_bet_to_match * 2 || gameState.big_blind * 2;
      setRaiseAmount(minRaise);

      // Show "Play Next Hand" button when game ends
      if (gameState.winner) {
        setShowPlayAgain(true);
      }
    }
  }, [gameState]);

  // ✅ THE FIX for a frozen game: If it's the bot's turn, automatically "poke" the backend.
  useEffect(() => {
    if (gameState && gameState.current_player_id === 'bot' && !gameState.winner) {
      // Use a small delay to make the bot's action feel more natural
      const timer = setTimeout(() => {
        handlePlayerAction('none'); // Send a "no action" to trigger the bot's turn
      }, 1000); // 1 second delay

      return () => clearTimeout(timer); // Cleanup timer on component re-render
    }
  }, [gameState]); // Re-run this check every time the gameState changes

  if (!gameState) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center bg-gray-900">
        <div className="flex flex-col items-center space-y-4">
          <h1 className="text-5xl font-bold text-white">Enigma Poker</h1>
          <button
            onClick={() => handleCreateGame(true)}
            className="px-8 py-4 bg-blue-600 hover:bg-blue-700 text-white font-bold rounded-lg text-2xl"
          >
            Start Game
          </button>
        </div>
      </main>
    );
  }

  const userPlayer = gameState.players.find((p) => p.id === 'user');
  const botPlayer = gameState.players.find((p) => p.id === 'bot');
  if (!userPlayer || !botPlayer) return <div>Loading...</div>;

  const isUserTurn = gameState.current_player_id === 'user' && !gameState.winner;
  const callAmount = gameState.current_bet_to_match - userPlayer.current_bet;
  const canCheck = callAmount <= 0;
  const showBotCards = !!gameState.winner || userPlayer.folded;

  return (
    <main className="flex min-h-screen w-full items-center justify-center bg-gray-900 text-white p-8 font-sans">
      <div className="grid grid-cols-3 grid-rows-1 gap-8 w-full max-w-screen-xl">
        {/* Col 1: Bot Info */}
        <div className="col-span-1 flex items-center justify-center">
          <PlayerInfo
            name="Enigma Bot"
            chips={botPlayer.chips}
            cards={botPlayer.hand}
            showCards={showBotCards}
            currentBet={botPlayer.current_bet}
            lastAction={botPlayer.last_action}
            isWinner={gameState.winner === 'bot'}
          />
        </div>

        {/* Col 2: Table */}
        <div className="col-span-1 flex flex-col items-center justify-center space-y-8">
          <div className="bg-black/40 px-6 py-3 rounded-lg shadow-lg">
            <h2 className="text-4xl font-bold text-yellow-300">Pot: ${gameState.pot}</h2>
          </div>
          <div className="flex space-x-3 h-28 items-center">
            {gameState.community_cards.map((card, i) => (
              <Card key={i} suit={card.suit} rank={card.rank} />
            ))}
          </div>
          <div className="h-24 flex items-center">
            {showPlayAgain && (
              <button
                onClick={() => handleCreateGame(false)}
                className="px-6 py-3 bg-green-600 hover:bg-green-700 text-white font-bold rounded-lg text-xl animate-pulse"
              >
                Play Next Hand
              </button>
            )}
          </div>
        </div>

        {/* Col 3: Your Info & Actions */}
        <div className="col-span-1 flex flex-col items-center justify-between">
          <PlayerInfo
            name="You"
            chips={userPlayer.chips}
            cards={userPlayer.hand}
            showCards={true}
            currentBet={userPlayer.current_bet}
            lastAction={userPlayer.last_action}
            isWinner={gameState.winner === 'user'}
          />

          <div className="flex flex-col space-y-4 p-4 bg-gray-800/70 rounded-xl w-full max-w-sm">
            <div className="grid grid-cols-3 gap-2">
              <button
                disabled={!isUserTurn}
                onClick={() => handlePlayerAction('fold')}
                className="px-4 py-3 bg-red-600 hover:bg-red-700 rounded-md font-bold text-lg disabled:bg-gray-500 disabled:cursor-not-allowed"
              >
                Fold
              </button>
              <button
                disabled={!isUserTurn}
                onClick={() => handlePlayerAction('call')}
                className="px-4 py-3 bg-gray-600 hover:bg-gray-700 rounded-md font-bold text-lg disabled:bg-gray-500 disabled:cursor-not-allowed"
              >
                {canCheck ? 'Check' : `Call $${callAmount}`}
              </button>
              <button
                disabled={!isUserTurn}
                onClick={() => handlePlayerAction('raise', raiseAmount)}
                className="px-4 py-3 bg-blue-600 hover:bg-blue-700 rounded-md font-bold text-lg disabled:bg-gray-500 disabled:cursor-not-allowed"
              >
                Raise
              </button>
            </div>
            <div className="flex flex-col items-center">
              <input
                type="range"
                min={gameState.current_bet_to_match * 2 || gameState.big_blind * 2}
                max={userPlayer.chips + userPlayer.current_bet}
                step={gameState.big_blind}
                value={raiseAmount}
                onChange={(e) => setRaiseAmount(Number(e.target.value))}
                className="w-full disabled:opacity-50"
                disabled={!isUserTurn}
              />
              <p className="font-mono mt-1 text-yellow-300 bg-black/30 px-3 rounded-full">${raiseAmount}</p>
            </div>
          </div>
        </div>
      </div>
    </main>
  );
}
