package com.exitguide.navigation.executor;

/** Rejects callbacks that belong to a stopped or superseded navigation episode. */
final class EpisodeGenerationGuard {
    private long generation;

    long reset() {
        generation++;
        return generation;
    }

    long current() {
        return generation;
    }

    boolean accepts(long callbackGeneration, boolean executorActive) {
        return executorActive && callbackGeneration == generation;
    }
}
