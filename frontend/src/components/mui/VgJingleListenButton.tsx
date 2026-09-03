"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";
import { CircularProgress, IconButton, Tooltip } from "@mui/material";
import PauseIcon from "@mui/icons-material/Pause";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { getJingleListenUrl } from "../../services/settingsApi";

export type VgJingleListenButtonProps = {
  /** Identifiant jingle MusicScreen (ex. tesla). */
  jingleId: string;
  /** Desactive le bouton (chargement catalogue). */
  disabled?: boolean;
};

/**
 * Lecture du MP3 jingle original a cote du selecteur.
 */
export function VgJingleListenButton({ jingleId, disabled }: VgJingleListenButtonProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);

  const stop = useCallback(() => {
    const el = audioRef.current;
    if (el) {
      el.pause();
      el.removeAttribute("src");
      el.load();
    }
    setPlaying(false);
  }, []);

  useEffect(() => {
    stop();
  }, [jingleId, stop]);

  useEffect(() => {
    const el = audioRef.current;
    if (!el) return;
    const onEnded = () => setPlaying(false);
    const onPause = () => setPlaying(false);
    const onPlay = () => setPlaying(true);
    el.addEventListener("ended", onEnded);
    el.addEventListener("pause", onPause);
    el.addEventListener("play", onPlay);
    return () => {
      el.removeEventListener("ended", onEnded);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("play", onPlay);
    };
  }, []);

  useEffect(() => () => stop(), [stop]);

  const toggle = async () => {
    const el = audioRef.current;
    if (!el || !jingleId) return;
    if (playing) {
      el.pause();
      return;
    }
    setLoading(true);
    try {
      el.src = getJingleListenUrl(jingleId);
      await el.play();
    } catch {
      stop();
    } finally {
      setLoading(false);
    }
  };

  const busy = loading || disabled;

  return (
    <>
      <Tooltip title={playing ? "Pause jingle" : "Ecouter le jingle (MP3 source, pas le rendu ligne)"}>
        <span>
          <IconButton
            size="small"
            color="primary"
            disabled={busy || !jingleId}
            onClick={() => void toggle()}
            aria-label="Ecouter le jingle"
          >
            {loading ? (
              <CircularProgress size={20} />
            ) : playing ? (
              <PauseIcon />
            ) : (
              <PlayArrowIcon />
            )}
          </IconButton>
        </span>
      </Tooltip>
      <audio ref={audioRef} preload="none" style={{ display: "none" }} />
    </>
  );
}
