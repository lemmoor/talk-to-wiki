import ChatBox from "./components/ChatBox";

export default function Home() {
  return (
    <div className="flex flex-1 items-center justify-center m-4">
      <div className="w-full max-w-7xl h-[calc(100dvh-2rem)]">
        <ChatBox />
      </div>
    </div>
  );
}
