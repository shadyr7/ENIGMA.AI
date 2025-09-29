'use client';

import { useState } from 'react';

// --- Reusable Components ---

const Card = ({ suit, rank, faceDown = false }) => {
  if (faceDown) {
    return <div className="w-14 h-20 bg-red-800 rounded-lg border-2 border-red-900 shadow-inner"></div>;
  }
  const suitColor = suit === '♥' || suit === '♦' ? 'text-red-500' : 'text-gray-900';
  return (
    <div className="w-14 h-20 bg-white rounded-lg flex flex-col justify-between p-1 border border-gray-300 shadow-lg">
      <span className={`text-sm font-bold ${suitColor}`}>{rank}</span>
      <span className={`text-2xl self-center ${suitColor}`}>{suit}</span>
      <span className={`text-sm font-bold self-end transform rotate-180 ${suitColor}`}>{rank}</span>
    </div>
  );
};

const Player = ({ name, chips, cards, isBot = false, currentBet = 0 }) => {
  return (
    <div className="flex flex-col items-center space-y-2 py-3 px-4 bg-gray-800/70 rounded-xl shadow-xl backdrop-blur-sm border border-gray-700/50">
      <div className="text-center">
        <p className="font-bold text-base text-white">{name}</p>
        <p className="text-yellow-400 font-mono text-sm">${chips}</p>
      </div>
      <div className="flex space-x-1 h-20 items-center">
        {cards.length > 0 ? (
          <>
            <Card suit={cards[0]?.suit} rank={cards[0]?.rank} faceDown={isBot} />
            <Card suit={cards[1]?.suit} rank={cards[1]?.rank} faceDown={isBot} />
          </>
        ) : (
          <>
            <Card faceDown={true} />
            <Card faceDown={true} />
          </>
        )}
      </div>
      {currentBet > 0 && (
        <div className="flex items-center space-x-2 bg-black/40 px-2 py-1 rounded-full border border-yellow-500/30">
          <div className="w-3 h-3 rounded-full bg-yellow-500 border border-yellow-300"></div>
          <p className="text-white font-mono text-xs">${currentBet}</p>
        </div>
      )}
    </div>
  );
};

// --- Main Page Component ---

export default function Home() {
  const [raiseAmount, setRaiseAmount] = useState(100);

  return (
    <main className="flex min-h-screen items-center justify-center bg-gradient-to-br from-gray-900 to-gray-800 text-white p-4 font-sans">
      <div className="w-full max-w-6xl aspect-[16/10] bg-gradient-to-br from-green-800 to-green-900 rounded-[50px] border-4 border-amber-700 shadow-2xl relative overflow-hidden">
        
        {/* Subtle felt texture overlay */}
        <div className="absolute inset-0 opacity-20 bg-[radial-gradient(circle_at_50%_50%,rgba(255,255,255,0.1),transparent_50%)]"></div>
        
        {/* Top Zone - Bot Player */}
        <div className="absolute top-4 left-1/2 -translate-x-1/2 z-30">
          <Player 
            name="Enigma Bot"
            chips={9850}
            cards={[]}
            isBot={true}
            currentBet={150}
          />
        </div>
        
        {/* Center Zone - Community Cards and Pot */}
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 flex flex-col items-center space-y-4 z-10">
          {/* Pot Display */}
          <div className="bg-black/50 px-6 py-2 rounded-xl shadow-lg border border-yellow-500/30 backdrop-blur-sm">
            <h2 className="text-xl font-bold text-yellow-300">Pot: $300</h2>
          </div>
          
          {/* Community Cards */}
          <div className="flex space-x-2 p-3 bg-black/20 rounded-xl backdrop-blur-sm">
            <Card suit="♥" rank="A" />
            <Card suit="♠" rank="K" />
            <Card suit="♦" rank="7" />
            <Card suit="♣" rank="2" />
            <Card faceDown={true} />
          </div>
        </div>
        
        {/* Bottom Zone - Human Player */}
        <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-30">
          <Player 
            name="Aaditya"
            chips={10150}
            cards={[{ suit: '♠', rank: 'A' }, { suit: '♣', rank: 'A' }]}
            isBot={false}
          />
        </div>
        
        {/* Right Zone - Action Controls */}
        <div className="absolute bottom-4 right-4 flex flex-col space-y-3 z-30">
          {/* Action Buttons */}
          <div className="flex flex-col space-y-2 p-3 bg-gray-800/80 rounded-xl shadow-xl backdrop-blur-sm border border-gray-600/50">
            <div className="flex space-x-2">
              <button 
                aria-label="Fold your hand" 
                className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-lg font-semibold transition-all shadow-lg hover:shadow-xl active:scale-95 text-sm"
              >
                Fold
              </button>
              <button 
                aria-label="Check the current bet" 
                className="px-4 py-2 bg-gray-500 hover:bg-gray-600 rounded-lg font-semibold transition-all shadow-lg hover:shadow-xl active:scale-95 text-sm"
              >
                Check
              </button>
              <button 
                aria-label="Raise the bet" 
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 rounded-lg font-semibold transition-all shadow-lg hover:shadow-xl active:scale-95 text-sm"
              >
                Raise
              </button>
            </div>
            
            {/* Bet Slider */}
            <div className="flex flex-col items-center pt-2 border-t border-gray-600/50">
              <input 
                type="range" 
                min="50" 
                max="10150" 
                step="50"
                value={raiseAmount}
                onChange={(e) => setRaiseAmount(Number(e.target.value))}
                className="w-full h-2 bg-gray-700 rounded-lg appearance-none cursor-pointer slider" 
                aria-label="Bet amount slider"
              />
              <p className="text-center font-mono mt-2 text-yellow-300 bg-black/40 px-3 py-1 rounded-full text-sm border border-yellow-500/30">
                ${raiseAmount}
              </p>
            </div>
          </div>
        </div>
        
      </div>
      
      <style jsx>{`
        .slider::-webkit-slider-thumb {
          appearance: none;
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #fbbf24;
          border: 2px solid #f59e0b;
          cursor: pointer;
          box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        }
        
        .slider::-moz-range-thumb {
          height: 16px;
          width: 16px;
          border-radius: 50%;
          background: #fbbf24;
          border: 2px solid #f59e0b;
          cursor: pointer;
          box-shadow: 0 2px 6px rgba(0,0,0,0.3);
        }
      `}</style>
    </main>
  );
}